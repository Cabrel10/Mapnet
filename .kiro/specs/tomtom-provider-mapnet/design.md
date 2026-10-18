# Design Document — `tomtom-provider-mapnet`

## Introduction

Ce document décrit l'architecture cible de l'intégration TomTom dans MAPNET.
La feature couvre deux phases indépendantes opérant sur deux microservices FastAPI distincts :

- **Phase 0 — Geocoding** : `services/places` reçoit `TomTomGeocodingProvider` et `NominatimProvider` derrière l'abstraction `GeocodingProvider`, les contrats de domaine `GeoResult`/`Address`, et l'endpoint `/api/v1/places/geocode`.
- **Phase 1 — Routing** : `services/routing` reçoit `TomTomRoutingProvider` comme troisième moteur derrière `RoutingProvider`, avec les contrats `Route`/`Step`/`ProviderMeta`.

**Règle architecturale centrale :** TomTom est un provider corollaire. Les fichiers
`overpass_client.py`, `osrm_client.py`, `valhalla_client.py` et le schéma PostGIS
restent intouchables. Les modifications à `main.py` sont minimales (injection
de provider + nouveau endpoint/paramètre).

---

## Architecture

### Vue d'ensemble

```
                        MAPNET
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    services/places  services/routing  (futur)
           │               │
    GeocodingService  RoutingService
           │               │
    ┌──────┴──────┐  ┌─────┴──────────┐
    │             │  │       │         │
 Nominatim    TomTom  Valhalla  OSRM  TomTom
 Provider     Geocoding  (existant)   Routing
    │             │         │              │
    └──────┬──────┘         └──────┬───────┘
           │                       │
    Contrat GeoResult        Contrat Route
    (domaine MAPNET)         (domaine MAPNET)
           │                       │
    endpoint /geocode        engine=tomtom
```

**Les contrats internes (`GeoResult`, `Route`) appartiennent à MAPNET.**
Aucune normalisation vers le format OSRM n'est effectuée.

### Microservice `services/places`

```
services/places/app/
├── errors.py                   ← Hiérarchie ProviderError
├── domain/
│   ├── __init__.py
│   └── geo_result.py           ← GeoResult, Address (dataclass)
├── providers/
│   ├── __init__.py
│   ├── base.py                 ← GeocodingProvider (ABC)
│   ├── nominatim.py            ← NominatimProvider (benchmark-only en Phase 0)
│   └── tomtom.py               ← TomTomGeocodingProvider
├── geocoder.py                 ← GeocodingService (orchestrateur)
└── main.py                     ← modification minimale (+/geocode)
```

### Microservice `services/routing`

```
services/routing/app/
├── errors.py                   ← Même hiérarchie ProviderError (dupliquée)
├── domain/
│   ├── __init__.py
│   └── route.py                ← Route, Step, ProviderMeta (dataclass)
├── providers/
│   ├── __init__.py
│   ├── base.py                 ← RoutingProvider (ABC)
│   └── tomtom.py               ← TomTomRoutingProvider
├── router.py                   ← RoutingService (orchestrateur)
└── main.py                     ← modification minimale (+engine=tomtom)
```

### Scripts

```
scripts/
├── benchmark_geocoding.py      ← benchmark symétrique TomTom + Nominatim
└── corpus_cameroun.json        ← ~250 requêtes structurées par axes

results/                        ← créé par le benchmark
```

---

## Composants

### `errors.py` — Hiérarchie ProviderError

Dupliquée dans les deux services (même noms, même sémantique). Pas de package
partagé inter-services pour conserver l'isolation microservice.

```python
class ProviderError(Exception): ...
class ProviderAuthError(ProviderError): ...         # 401/403 — pas de retry
class ProviderRateLimitError(ProviderError): ...    # 429 — pas de retry
class ProviderTimeoutError(ProviderError): ...      # timeout — retry contrôlé
class ProviderTemporaryUnavailable(ProviderError): ... # 5xx — retry contrôlé
class ProviderNoResult(ProviderError): ...          # réponse valide, 0 résultat
class ProviderResponseError(ProviderError): ...     # réponse malformée
```

**Note sur `ProviderNoResult` :** représente une réponse HTTP valide du provider
sans résultat exploitable. Il ne s'agit pas d'une panne — ne pas traiter comme
une erreur dans les logs/monitoring. En mode `provider=auto`, déclenche un
fallback vers PostGIS sans lever d'erreur HTTP.

**Règle de retry par type :**

| Erreur | Retry autorisé | Fallback |
|---|---|---|
| `ProviderAuthError` | Non | Désactiver provider |
| `ProviderRateLimitError` | Non | Pas de substitution silencieuse |
| `ProviderTimeoutError` | Oui (max_retries) | `fallback_used: true` |
| `ProviderTemporaryUnavailable` | Oui (max_retries) | `fallback_used: true` |
| `ProviderNoResult` | Non | Fallback si `provider=auto` |
| `ProviderResponseError` | Non | `fallback_used: true` |

---

### `domain/geo_result.py` — Contrats domaine geocoding

```python
@dataclass
class Address:
    display_name: str                   # obligatoire
    street: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    postcode: Optional[str] = None

@dataclass
class GeoResult:
    latitude: float
    longitude: float
    address: Address
    provider: str                       # "nominatim" | "tomtom"
    mapnet_confidence: float = 0.0      # heuristique MAPNET, non calibrée
    provider_confidence: Optional[float] = None   # score brut provider
    distance_m: Optional[float] = None
    source_id: Optional[str] = None
    raw: Optional[dict] = field(default=None, repr=False)  # jamais exposé en HTTP
```

**Important :** `mapnet_confidence` et `provider_confidence` ne sont pas
comparables entre providers distincts. `raw` est exclu de toute réponse HTTP.

---

### `domain/route.py` — Contrats domaine routing

```python
@dataclass
class ProviderMeta:
    provider: str                       # "osrm" | "valhalla" | "tomtom"
    fallback_used: bool = False
    fallback_provider: Optional[str] = None
    traffic: bool = False
    data_freshness: str = "static"      # "static" | "realtime"

@dataclass
class Step:
    instruction: str
    maneuver: str
    modifier: str
    location: List[float]               # [lon, lat] — ordre GeoJSON
    distance: float                     # mètres
    duration: float                     # secondes
    name: str = ""

@dataclass
class Route:
    distance: float                     # mètres
    duration: float                     # secondes
    geometry: dict                      # GeoJSON LineString
    steps: List[Step] = field(default_factory=list)
    provider_meta: Optional[ProviderMeta] = None
    badges: dict = field(default_factory=dict)
```

---

### `providers/base.py` — Interfaces abstraites

```python
class GeocodingProvider(ABC):
    name: str

    @abstractmethod
    def geocode(self, query: str, limit: int = 5,
                lat: Optional[float] = None,
                lon: Optional[float] = None) -> List[GeoResult]: ...

    @abstractmethod
    def reverse_geocode(self, lat: float, lon: float) -> Optional[GeoResult]: ...


class RoutingProvider(ABC):
    name: str

    @abstractmethod
    def route(self, from_lat: float, from_lon: float,
              to_lat: float, to_lon: float,
              costing: str = "auto") -> Route: ...

    @abstractmethod
    def available(self) -> bool: ...
```

---

### `providers/tomtom.py` (places) — TomTomGeocodingProvider

**Initialisation :**
- Lit `TOMTOM_API_KEY` depuis `os.environ`. Si absente ou vide : `ProviderAuthError` immédiate.
- Crée un `httpx.Client` unique à l'instanciation, réutilisé pour toutes les requêtes.
- Expose `close()` et supporte le protocol context manager (`__enter__` / `__exit__`).
- Paramètres configurables : `timeout: float = 10.0`, `max_retries: int = 2`.

**Méthode `geocode(query, limit, lat, lon)`:**
1. Encode `query` avec `urllib.parse.quote(query, safe="")` (RFC 3986).
2. Construit l'URL : `https://api.tomtom.com/search/2/search/{encoded_query}.json`
3. Passe `countrySet=CMR`, `language=fr-FR` dans les paramètres systématiquement.
4. Appelle `_get(url, params)`.
5. Normalise chaque item via `_to_geo_result()` → `List[GeoResult]`.

**Méthode `reverse_geocode(lat, lon)`:**
1. Construit l'URL : `https://api.tomtom.com/search/2/reverseGeocode/{lat},{lon}.json`
2. Appelle `_get(url, params)`.
3. Normalise via `_to_geo_result_reverse()` — parsing défensif du champ `position`.

**Parsing défensif `position` (reverse geocoding) :**

```python
# Le champ position peut être une chaîne "lat,lon" ou un dict {"lat":..,"lon":..}
if isinstance(pos_raw, dict):
    rlat = float(pos_raw["lat"])
    rlon = float(pos_raw["lon"])
elif isinstance(pos_raw, str) and pos_raw:
    parts = pos_raw.split(",")
    if len(parts) != 2:
        raise ProviderResponseError(...)
    rlat, rlon = float(parts[0]), float(parts[1])
else:
    raise ProviderResponseError(...)
```
Toute valeur non parsable lève `ProviderResponseError` — jamais de coordonnées `0.0, 0.0` silencieuses.

**Calcul `mapnet_confidence` (heuristique non calibrée) :**

```python
type_scores = {
    "PointAddress": 0.90, "POI": 0.80, "MunicipalitySubdivision": 0.65,
    "AddressRange": 0.70, "Street": 0.60, "Municipality": 0.55, "Country": 0.30,
}
score = type_scores.get(entity_type, 0.50)

# Les bonus rue+ville et pays Cameroun ne s'appliquent PAS au type Country.
# Country retourne toujours 0.30 — aucun bonus possible.
# Cela garantit la Property 7 : Country confidence = 0.30 exactement.
if entity_type != "Country":
    if addr.get("streetName") and addr.get("localName"):
        score = min(score + 0.05, 1.0)   # bonus rue+ville
    if addr.get("countryCode") in ("CM", "CMR"):
        score = min(score + 0.05, 1.0)   # bonus Cameroun
```

⚠️ Ces coefficients sont des estimations initiales non calibrées sur des données
réelles camerounaises. Ils seront recalibrés après le benchmark (§ Benchmark).
`mapnet_confidence` ne doit pas servir à comparer TomTom et Nominatim dans le
benchmark — utiliser `top1_lat_ok`, `address_complete`, `result_found`.

**Méthode `_get(url, params)` — gestion HTTP :**

```
pour attempt de 0 à max_retries :
    GET url
    si 401 ou 403 → ProviderAuthError (pas de retry)
    si 429        → ProviderRateLimitError (pas de retry)
    si 5xx        → si dernier attempt : ProviderTemporaryUnavailable
                    sinon : log WARNING, continuer
    si TimeoutException → si dernier attempt : ProviderTimeoutError
                          sinon : log WARNING, continuer
    sinon : r.raise_for_status() ; return r.json()
```

---

### `providers/nominatim.py` — NominatimProvider

**Rôle dans Phase 0 :** `NominatimProvider` est introduit exclusivement pour le
benchmark symétrique TomTom/Nominatim. Il n'est PAS utilisé par `provider=auto`
dans `GeocodingService`. `provider=auto` utilise TomTom → fallback PostGIS.

Implémente `GeocodingProvider` avec les mêmes signatures.

- `geocode()` : appelle l'API Nominatim `/search` avec `q`, `format=jsonv2`, `countrycodes=cm`.
- `reverse_geocode()` : appelle `/reverse` avec `lat`, `lon`, `format=jsonv2`.
- Normalise vers `GeoResult` avec `provider="nominatim"`.
- `mapnet_confidence` calculée selon les champs `type` / `class` Nominatim (heuristique distincte).
- URL de base configurable via `NOMINATIM_URL` (défaut : `https://nominatim.openstreetmap.org`).
- `User-Agent` configurable via `NOMINATIM_USER_AGENT` (défaut : `MAPNET/1.0`).
- Respecte les règles de politesse Nominatim : `User-Agent` obligatoire, délai configurable entre requêtes (défaut : 1 s).

---

### `providers/tomtom.py` (routing) — TomTomRoutingProvider

**Initialisation :**
- Lit `TOMTOM_API_KEY`. Si absente : `self._api_key = ""`. Pas d'exception.
- `available()` retourne `bool(self._api_key)`.

**Mapping des profils costing :**

```python
_COSTING_MAP = {
    "auto": "car", "car": "car",
    "motorcycle": "motorcycle",
    "bicycle": "bicycle",
    "pedestrian": "pedestrian", "foot": "pedestrian",
}
```

**Méthode `route()` :**
1. URL : `https://api.tomtom.com/routing/1/calculateRoute/{from_lat},{from_lon}:{to_lat},{to_lon}/json`
2. Paramètres : `travelMode`, `traffic=true`, `language=fr-FR`, `instructionsType=text`, `routeRepresentation=polyline`.
3. Gestion HTTP identique au provider geocoding (401/403/429/5xx/timeout).
4. Normalisation via `_normalize(data)` → `Route`.

**Normalisation `_normalize()` :**
- Géométrie : parcourt `routes[0].legs[].points[]`, construit `[[lon, lat], ...]` (ordre GeoJSON).
- Steps : parcourt `routes[0].guidance.instructions[]`, construit `Step` par instruction.
- `ProviderMeta` : `provider="tomtom"`, `traffic=True`, `data_freshness="realtime"`.
  Ces champs reflètent que la requête a été envoyée avec `traffic=true`. Ils ne
  garantissent pas que des données trafic temps réel étaient disponibles pour
  le tronçon calculé par TomTom.
- Si `routes` vide : `ProviderNoResult`.

⚠️ Jamais de normalisation vers le format OSRM.

---

### `geocoder.py` — GeocodingService

Orchestre les providers pour l'endpoint `/geocode`.

```python
class GeocodingService:
    def __init__(self,
                 tomtom: Optional[TomTomGeocodingProvider],
                 nominatim: Optional[NominatimProvider],
                 local_search: Callable):
        """
        local_search : callable (q, lat, lon) -> dict
            Injecté depuis main.py pour déléguer au PostGIS existant sans
            créer de dépendance inverse (GeocodingService → main.py).
            Typiquement : local_search=search_places
        """
        self._tomtom = tomtom
        self._nominatim = nominatim
        self._local_search = local_search

    def geocode(self, query: str, provider: str = "auto",
                lat: Optional[float] = None,
                lon: Optional[float] = None) -> dict:
        """
        provider=tomtom : TomTom uniquement → 502 si ProviderError ou si non instancié
        provider=local  : PostGIS uniquement (via self._local_search)
        provider=auto   : TomTom si disponible → PostGIS si ProviderError
        Retourne: {"status", "provider", "fallback_used", "results"}
        """
```

Logique de sélection :

```
si provider in ("auto", "tomtom") et tomtom instancié :
    essayer tomtom.geocode()
    si succès → retourner {"provider": "tomtom", "fallback_used": false, ...}
    si ProviderNoResult et provider=="auto" → continuer vers PostGIS
    si ProviderError et provider=="tomtom" → lever HTTPException(502, message générique)
    si ProviderError et provider=="auto" → log WARNING, continuer vers PostGIS

si provider=="tomtom" et tomtom non instancié :
    lever HTTPException(502, "TomTom geocoding non disponible")

si provider=="local" ou fallback :
    résultat PostGIS via self._local_search()
    retourner {"provider": "local", "fallback_used": (provider=="auto"), ...}
```

**Règle d'exposition des erreurs :** les messages d'erreur HTTP TomTom ne doivent
jamais apparaître dans les corps de réponse FastAPI. Utiliser des messages génériques
et logger les détails en interne.

---

### `router.py` — RoutingService

```python
class RoutingService:
    def __init__(self, tomtom: Optional[TomTomRoutingProvider]):
        self._tomtom = tomtom

    def route(self, from_lat, from_lon, to_lat, to_lon,
              engine: str, costing: str) -> dict:
        """
        engine=tomtom : TomTomRoutingProvider → 502 si ProviderError ou non instancié
        engine=auto   : conserve comportement Valhalla→OSRM (tomtom ignoré si indisponible)
        engine=valhalla / osrm : délégue à l'existant, inchangé
        """
```

---

### Modifications `main.py` (places)

**Ajouts uniquement :**

```python
# Initialisation optionnelle au démarrage
_tomtom_geocoder: Optional[TomTomGeocodingProvider] = None
_nominatim_provider: Optional[NominatimProvider] = None

def _init_providers():
    global _tomtom_geocoder, _nominatim_provider
    try:
        _tomtom_geocoder = TomTomGeocodingProvider()
    except ProviderAuthError:
        logger.info("TOMTOM_API_KEY absente — provider TomTom désactivé")
    _nominatim_provider = NominatimProvider()

# ATTENTION avant modification : vérifier si main.py utilise déjà un handler
# @app.on_event("startup") ou un lifespan asynccontextmanager. Si oui,
# intégrer _init_providers() dans le mécanisme existant plutôt que créer
# un deuxième handler qui pourrait être ignoré selon la version de FastAPI.
@app.on_event("startup")
async def startup():
    _init_providers()

@app.get("/api/v1/places/geocode")
def geocode(q: str, lat: Optional[float] = None, lon: Optional[float] = None,
            provider: str = "auto"):
    svc = GeocodingService(_tomtom_geocoder, _nominatim_provider,
                           local_search=search_places)
    return svc.geocode(q, provider=provider, lat=lat, lon=lon)
```

Aucune modification des endpoints existants. Signatures et réponses inchangées.

---

### Modifications `main.py` (routing)

**Ajouts uniquement :**

```python
_tomtom_router: Optional[TomTomRoutingProvider] = None

# ATTENTION avant modification : vérifier si main.py utilise déjà un handler
# @app.on_event("startup") ou un lifespan asynccontextmanager. Si oui,
# intégrer dans le mécanisme existant.
@app.on_event("startup")
async def startup():
    global _tomtom_router
    p = TomTomRoutingProvider()
    if p.available():
        _tomtom_router = p

# Dans calculate_route() — ajout du cas engine=tomtom :
if engine == "tomtom":
    if _tomtom_router is None:
        raise HTTPException(502, detail="TomTom routing non disponible")
    try:
        r = _tomtom_router.route(...)
        return {"status": "ok", "engine": "tomtom",
                "traffic": True, "data_freshness": "realtime", ...}
    except ProviderAuthError:
        raise HTTPException(502, detail="TomTom routing: provider non autorisé")
    except ProviderRateLimitError:
        raise HTTPException(502, detail="TomTom routing: quota atteint")
    except ProviderError:
        raise HTTPException(502, detail="TomTom routing indisponible")
        # Les détails techniques sont loggés en interne, jamais exposés au client.
# engine=auto/valhalla/osrm → comportement existant inchangé
```

---

## Interfaces HTTP

### Endpoint `GET /api/v1/places/geocode`

**Paramètres :**
- `q` (str, requis) — requête textuelle
- `lat` (float, optionnel) — latitude de contexte
- `lon` (float, optionnel) — longitude de contexte
- `provider` (str, optionnel, défaut `"auto"`) — `"auto"` | `"tomtom"` | `"local"`

**Réponse :**
```json
{
  "status": "ok",
  "provider": "tomtom",
  "fallback_used": false,
  "results": [
    {
      "latitude": 3.8627,
      "longitude": 11.5078,
      "address": {
        "display_name": "Université de Yaoundé I, Yaoundé, Cameroun",
        "street": null,
        "city": "Yaoundé",
        "region": "Centre",
        "country": "Cameroun",
        "postcode": null
      },
      "provider": "tomtom",
      "mapnet_confidence": 0.9,
      "provider_confidence": 7.852
    }
  ]
}
```

Note : `raw` absent de la réponse. `provider_confidence` est le score brut TomTom
(non comparable à Nominatim).

**Codes HTTP :**
- `200` — succès (y compris résultats vides)
- `502` — TomTom indisponible ou non instancié avec `provider=tomtom`

### Paramètre `engine=tomtom` sur `/api/v1/routing/route`

```json
{
  "status": "ok",
  "engine": "tomtom",
  "traffic": true,
  "data_freshness": "realtime",
  "routes": [...]
}
```

**Codes HTTP :**
- `200` — succès
- `502` — TomTom indisponible, non instancié, ou erreur provider avec `engine=tomtom`

---

## Flux de données

### Geocoding `provider=auto`

```
Client
  │ GET /api/v1/places/geocode?q=Yaoundé&provider=auto
  ▼
main.py → GeocodingService.geocode()
  │
  ├─ TomTomGeocodingProvider instancié ?
  │     OUI
  │       ├─ quote("Yaoundé") → "Yaound%C3%A9"
  │       ├─ GET api.tomtom.com/search/2/search/Yaound%C3%A9.json
  │       │   ?countrySet=CMR&language=fr-FR&key=...
  │       ├─ _to_geo_result() × N → List[GeoResult]
  │       └─ {"provider":"tomtom","fallback_used":false,"results":[...]}
  │     ERREUR ProviderError
  │       └─ log WARNING → continuer vers PostGIS
  │
  └─ self._local_search() → PostGIS search_places()
        → {"provider":"local","fallback_used":true,"results":[...]}
```

### Routing `engine=tomtom`

```
Client
  │ POST /api/v1/routing/route?engine=tomtom
  ▼
main.py → TomTomRoutingProvider.route()
  │
  ├─ GET api.tomtom.com/routing/1/calculateRoute/{coords}/json
  │   ?travelMode=car&traffic=true&language=fr-FR&key=...
  ├─ _normalize(data) :
  │     legs[].points[] → [[lon,lat],...] (GeoJSON LineString)
  │     guidance.instructions[] → [Step, ...]
  │     ProviderMeta(traffic=True, data_freshness="realtime")
  │     [reflète le paramètre demandé, pas une garantie trafic]
  └─ {"engine":"tomtom","traffic":true,"data_freshness":"realtime","routes":[...]}
```

---

## Modèle d'erreur

### Séquence de gestion HTTP dans `_get()`

```
attempt = 0
┌─────────────────────────────────────────────────────┐
│ GET url                                              │
│                                                      │
│  status 401/403 ──────────────► ProviderAuthError ◄─┤ (pas de retry)
│  status 429 ──────────────────► ProviderRateLimitError (pas de retry)
│  status 5xx                                          │
│    attempt < max_retries ──────► log WARNING         │
│    attempt == max_retries ─────► ProviderTemporaryUnavailable
│  TimeoutException                                    │
│    attempt < max_retries ──────► log WARNING         │
│    attempt == max_retries ─────► ProviderTimeoutError
│  succès ──────────────────────► return r.json()      │
└─────────────────────────────────────────────────────┘
         attempt += 1; goto boucle
```

### Traduction FastAPI

Les `ProviderError` sont interceptées dans `main.py` et traduites :
- `ProviderAuthError` / `ProviderRateLimitError` : `HTTP 502`, message générique.
- `ProviderError` avec `provider=auto` : fallback PostGIS/Valhalla, `fallback_used: true`.
- `ProviderError` avec `provider=tomtom` ou `engine=tomtom` : `HTTP 502` avec message générique. Les détails techniques (type d'erreur, status HTTP TomTom, message interne) sont loggés en interne et ne sont jamais exposés dans le corps de la réponse HTTP.

---

## Benchmark Cameroun

### Corpus `corpus_cameroun.json`

Structure par axes expérimentaux (~250 entrées). Chaque entrée porte ses axes comme `tags` et une tolérance géographique explicite :

```json
[
  {
    "query": "Université de Yaoundé I",
    "tags": ["urbain_yaounde", "francophone", "nom_officiel", "poi"],
    "ground_truth": {"lat": 3.8627, "lon": 11.5078},
    "ground_truth_tolerance_m": 100,
    "manual_evaluation": null
  },
  {
    "query": "Lycée Technique de Bafoussam",
    "tags": ["secondaire", "francophone", "nom_officiel", "poi"],
    "ground_truth": {"lat": 5.4769, "lon": 10.4165},
    "ground_truth_tolerance_m": 250,
    "manual_evaluation": null
  },
  {
    "query": "Ntui",
    "tags": ["rural", "francophone", "nom_officiel"],
    "ground_truth": {"lat": 4.4545, "lon": 11.6359},
    "ground_truth_tolerance_m": 500,
    "manual_evaluation": null
  },
  {
    "query": "derrière la pharmacie du marché central Yaoundé",
    "tags": ["urbain_yaounde", "francophone", "adresse_informelle"],
    "ground_truth": null,
    "ground_truth_tolerance_m": null,
    "manual_evaluation": {"useful": null, "location_error_m": null, "notes": ""}
  }
]
```

**Axes :**
- Géographique : `urbain_yaounde`, `urbain_douala`, `secondaire`, `rural`
- Linguistique : `francophone`, `anglophone`
- Toponymique : `nom_officiel`, `variante_ortho`, `nom_local`
- Type : `poi`, `adresse_formelle`, `adresse_informelle`, `reverse`

**Seuils de validation géographique (défauts si `ground_truth_tolerance_m` absent) :**
- Tag `urbain_*` : `distance_gt_m ≤ 100 m` → `top1_lat_ok = True`
- Tag `secondaire` : `distance_gt_m ≤ 250 m` → `top1_lat_ok = True`
- Tag `rural` : `distance_gt_m ≤ 500 m` → `top1_lat_ok = True`

### Script `benchmark_geocoding.py`

- Exécution symétrique : les deux providers reçoivent les mêmes requêtes dans le même ordre.
- Protocole : warm-up de 5 requêtes, puis alternance TomTom q_i / Nominatim q_i pour réduire le biais temporel de latence.
- Métriques par requête et par provider : `result_found`, `top1_lat_ok`, `top5_lat_ok` (+ `top5_rank`), `address_complete`, `city_correct`, `response_time_ms`, `distance_gt_m`, `error`, `http_status`.
- `mapnet_confidence` enregistrée mais **jamais utilisée pour comparer** les providers.
- Résumé console : `result_found (%)`, `top1_lat_ok (%)`, `top5_lat_ok (%)`, `address_complete (%)`, `latency_mean_ms`, `latency_p50_ms`, `latency_p95_ms`, `http_429_count`, `http_5xx_count`, `timeout_count` par provider.
- `manual_evaluation` préservé depuis le corpus vers les résultats, jamais écrasé.
- Sortie : fichier JSON détaillé dans `results/` + résumé console.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1 : Auth errors are never retried

*For any* HTTP status code in {401, 403}, when the TomTom HTTP client returns that status, the provider SHALL raise `ProviderAuthError` and the underlying HTTP client SHALL have been called exactly once (no retry).

**Validates: Requirements 1.3**

---

### Property 2 : 5xx errors exhaust retries before raising

*For any* HTTP 5xx status code (500–599) and any `max_retries` value n ≥ 0, the provider SHALL make exactly n + 1 HTTP attempts before raising `ProviderTemporaryUnavailable`.

**Validates: Requirements 1.5**

---

### Property 3 : Timeout errors exhaust retries before raising

*For any* `max_retries` value n ≥ 0, when every HTTP attempt raises `TimeoutException`, the provider SHALL make exactly n + 1 attempts before raising `ProviderTimeoutError`.

**Validates: Requirements 1.6**

---

### Property 4 : Malformed position raises ProviderResponseError

*For any* reverse geocode response where the `position` field cannot be parsed (None, empty string, malformed string, wrong type, missing required dict keys), the provider SHALL raise `ProviderResponseError` and SHALL NOT return coordinates `(0.0, 0.0)` silently.

**Validates: Requirements 1.7, 3.9**

---

### Property 5 : mapnet_confidence is independent of provider_confidence

*For any* TomTom response item, modifying the raw `score` field while keeping `entityType` and `address` fields constant SHALL produce the same `mapnet_confidence` value in the resulting `GeoResult`.

**Validates: Requirements 2.3, 2.4**

---

### Property 6 : PointAddress base confidence is always 0.90

*For any* TomTom response item with `entityType = "PointAddress"`, the base score assigned before any bonus SHALL be exactly 0.90. After optional address (+0.05) and country (+0.05) bonuses, the produced `GeoResult.mapnet_confidence` SHALL be ≥ 0.90 and ≤ 1.0.

**Validates: Requirements 2.5**

---

### Property 7 : Country confidence is always exactly 0.30

*For any* TomTom response item with `entityType = "Country"`, regardless of address fields (street, city, country code), the produced `GeoResult.mapnet_confidence` SHALL be exactly 0.30. No bonus is applied to the `Country` type.

**Validates: Requirements 2.6**

---

### Property 8 : raw field never appears in API response

*For any* `GeoResult` with a non-None `raw` field, serializing it to the HTTP response dict (as returned by the `/geocode` endpoint) SHALL NOT include a `"raw"` key at any nesting level of the response body. This includes nested objects (e.g., `results[i].raw`). A recursive inspection of the serialized JSON dict SHALL find no key equal to `"raw"` at any depth.

**Validates: Requirements 2.7**

---

### Property 9 : Cameroon bias is always applied

*For any* call to `TomTomGeocodingProvider.geocode()` with any query string, the resulting HTTP request parameters SHALL always include `countrySet=CMR` and `language=fr-FR`.

**Validates: Requirements 3.10**

---

### Property 10 : URL encoding of geocode queries

*For any* query string, the URL path used for the TomTom geocoding request SHALL contain `urllib.parse.quote(query, safe="")` as the encoded path segment, preserving all RFC 3986 percent-encoding rules.

**Validates: Requirements 3.7**

---

### Property 11 : Reverse geocode position parsing is format-agnostic

*For any* valid (lat, lon) coordinate pair, constructing a TomTom reverse geocode response with `position` as the string `"lat,lon"` and with `position` as the dict `{"lat": lat, "lon": lon}` SHALL produce `GeoResult` objects with identical `latitude` and `longitude` values.

**Validates: Requirements 3.8**

---

### Property 12 : provider_confidence equals raw score exactly

*For any* TomTom search result item containing a `score` field with value s, the produced `GeoResult.provider_confidence` SHALL equal `float(s)` exactly.

**Validates: Requirements 2.4**

---

### Property 13 : TomTom routing metadata reflects traffic-requested mode

*For any* successful call to `TomTomRoutingProvider.route()` with any origin/destination pair and any costing value, the produced `Route.provider_meta.traffic` SHALL be `True` and `Route.provider_meta.data_freshness` SHALL be `"realtime"`, reflecting that the HTTP request was sent with `traffic=true`. These values do not guarantee that real-time traffic data was available for the computed route segment.

**Validates: Requirements 6.5**

---

### Property 14 : Costing map covers all MAPNET profiles

*For any* costing value in `{"auto", "car", "motorcycle", "bicycle", "pedestrian", "foot"}`, the TomTom HTTP request SHALL use the expected `travelMode` value from the defined mapping.

**Validates: Requirements 7.4**

---

### Property 15 : GeoJSON coordinate order is [lon, lat]

*For any* TomTom routing response with leg points having `latitude` and `longitude` fields, the produced `Route.geometry.coordinates` list SHALL contain entries in `[longitude, latitude]` order (GeoJSON convention).

**Validates: Requirements 7.5**

---

### Property 16 : Step count matches instruction count

*For any* TomTom routing response with a `guidance.instructions` list of length N, the produced `Route.steps` list SHALL have exactly N entries.

**Validates: Requirements 7.6**

---

### Property 17 : engine=tomtom errors return HTTP 502 without fallback

*For any* `ProviderError` subclass raised by `TomTomRoutingProvider` when `engine=tomtom` is requested, the `/api/v1/routing/route` endpoint SHALL return HTTP 502 and SHALL NOT invoke Valhalla or OSRM as fallback.

**Validates: Requirements 8.3**

---

### Property 18 : provider=auto TomTom fallback propagates correctly

*For any* `ProviderError` subclass raised by `TomTomGeocodingProvider` when `provider=auto` is requested, the `/api/v1/places/geocode` endpoint SHALL return `"provider": "local"` and `"fallback_used": true` without raising an HTTP error.

**Validates: Requirements 4.5**

---

### Property 19 : Haversine distance and tolerance are consistent

*For any* result coordinates `(rlat, rlon)`, ground truth `(gtlat, gtlon)`, and corpus entry with `ground_truth_tolerance_m = t`, the benchmark's `distance_gt_m` SHALL equal the haversine distance between the two points (in metres), and `top1_lat_ok` SHALL equal `distance_gt_m ≤ t`. When `ground_truth_tolerance_m` is absent, the default tolerance is 100 m for `urbain_*` tags, 250 m for `secondaire` tags, and 500 m for `rural` tags.

**Validates: Requirements 5.4**

---

### Property 20 : Corpus entries have required fields

*For any* entry in `corpus_cameroun.json`, the entry SHALL contain the keys `query`, `tags`, `ground_truth`, `ground_truth_tolerance_m`, and `manual_evaluation`.

**Validates: Requirements 5.3**

---

### Property 21 : Existing endpoint response schemas are preserved

*For any* valid request to each of the 8 protected endpoints (`/search`, `/nearby`, `/nearest-district`, `/by-category`, `/building-at`, `/status`, `/categories`, `/layer-counts`), the response JSON SHALL contain the same top-level keys as before the TomTom integration (`"status"`, `"count"`, `"results"` or equivalent), with no new required fields added and no existing fields removed or renamed.

**Validates: Requirements 9.7, 4.9**

---

## Stratégie de tests

### Tests unitaires (pytest)

| Module | Ce qui est testé |
|---|---|
| `errors.py` | Hiérarchie d'héritage |
| `domain/geo_result.py` | Instantiation, champs optionnels |
| `domain/route.py` | Instantiation, valeurs par défaut |
| `providers/tomtom.py` (places) | Parsing position, confidence, erreurs HTTP, encodage URL, retry |
| `providers/tomtom.py` (routing) | Normalisation GeoJSON, steps, ProviderMeta, costing map |
| `geocoder.py` | Logique provider=auto/tomtom/local, local_search injection |
| `main.py` | Endpoint /geocode, engine=tomtom |

### Tests de propriétés (hypothesis)

Chaque propriété du § Correctness Properties correspond à un test hypothesis.
Minimum 100 itérations par propriété. Les appels HTTP sont mockés avec `unittest.mock.patch`.

**Exemple (Property 2) :**
```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(status_code=st.integers(min_value=500, max_value=599),
       max_retries=st.integers(min_value=0, max_value=3))
@settings(max_examples=100)
def test_5xx_exhausts_retries(status_code, max_retries, mock_http):
    mock_http.return_value.status_code = status_code
    provider = TomTomGeocodingProvider(api_key="x", max_retries=max_retries)
    with pytest.raises(ProviderTemporaryUnavailable):
        provider.geocode("test")
    assert mock_http.call_count == max_retries + 1
```

### Tests d'intégration

- Démarrage des services sans `TOMTOM_API_KEY` : vérifier que les 8 endpoints existants répondent normalement.
- Démarrage avec `TOMTOM_API_KEY` valide : vérifier que `/geocode?provider=tomtom` retourne des résultats.

---

## Séquence d'implémentation

```
1. errors.py (places + routing) — hiérarchie ProviderError
2. domain/geo_result.py — GeoResult, Address
3. domain/route.py — Route, Step, ProviderMeta
4. providers/base.py (places + routing) — interfaces ABC
5. providers/tomtom.py (places) — TomTomGeocodingProvider
   └─ tests unitaires + property tests
6. providers/nominatim.py — NominatimProvider (benchmark-only)
7. geocoder.py — GeocodingService (avec local_search injecté)
8. main.py (places) — ajout /geocode minimal
9. providers/tomtom.py (routing) — TomTomRoutingProvider
   └─ tests unitaires + property tests
10. router.py — RoutingService
11. main.py (routing) — ajout engine=tomtom minimal
12. scripts/corpus_cameroun.json — ~250 entrées avec ground_truth_tolerance_m
13. scripts/benchmark_geocoding.py
```

Aucune étape ne modifie `overpass_client.py`, `osrm_client.py`,
`valhalla_client.py` ni le schéma PostGIS.
