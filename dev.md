# MAPNET — Intégration TomTom : Analyse, Architecture et Spec

> **Document de développement interne**
> Statut : Brouillon de travail — en attente de benchmark réel
> Dernière mise à jour : 2026-09-29
> Révision 2 : corrections URL geocoding, client HTTP, confidence non calibré, benchmark symétrique, corpus structuré par axes

---

## Table des matières

1. [Définition TomTom dans le contexte MAPNET](#1-définition-tomtom-dans-le-contexte-mapnet)
2. [Ce que TomTom est — et ce qu'il n'est pas pour MAPNET](#2-ce-que-tomtom-est--et-ce-quil-nest-pas-pour-mapnet)
3. [Analyse critique du document précédent](#3-analyse-critique-du-document-précédent)
4. [Architecture cible MAPNET avec TomTom](#4-architecture-cible-mapnet-avec-tomtom)
5. [Spec — Phase 0 : TomTomProvider corollaire de Nominatim](#5-spec--phase-0--tomtomprovider-corollaire-de-nominatim)
6. [Spec — Phase 1 : TomTomProvider routing corollaire de OSRM/Valhalla](#6-spec--phase-1--tomtomprovider-routing-corollaire-de-osrmvalhalla)
7. [Benchmark Cameroun : corpus et méthode](#7-benchmark-cameroun--corpus-et-méthode)
8. [Modèle d'erreur requis](#8-modèle-derreur-requis)
9. [Séquence d'implémentation recommandée](#9-séquence-dimplémentation-recommandée)
10. [Ce qui ne sera PAS fait dans cette phase](#10-ce-qui-ne-sera-pas-fait-dans-cette-phase)
11. [Fichiers concernés](#11-fichiers-concernés)
12. [Décision finale : grille d'évaluation](#12-décision-finale--grille-dévaluation)

---

## 1. Définition TomTom dans le contexte MAPNET

### 1.1 Qu'est-ce que TomTom ?

TomTom est une société néerlandaise de cartographie et de données de localisation. Elle expose ses capacités sous forme d'APIs REST et de SDK mobiles (Android / iOS). Pour MAPNET, ce sont exclusivement les **APIs REST** qui sont pertinentes — pas les SDK mobiles.

Les APIs TomTom se regroupent en quatre familles :

| Famille          | Capacités exposées                                                                 | Pertinence MAPNET      |
|------------------|------------------------------------------------------------------------------------|------------------------|
| **Search**       | Geocoding, reverse geocoding, autocomplete, POI search, fuzzy search               | ✅ Haute (corollaire Nominatim) |
| **Routing**      | Calcul d'itinéraire, alternatives, trafic, optimisation waypoints, guidage          | ✅ Haute (corollaire OSRM/Valhalla) |
| **Traffic**      | Incidents, flux, vitesses temps réel                                                | 🟡 Moyenne (future couche données) |
| **Map Display**  | Tuiles vectorielles/raster, rendu cartographique (API Orbis — Public Preview 2026)  | ❌ Hors scope phase actuelle |

### 1.2 Pourquoi TomTom est pertinent pour MAPNET

MAPNET est un système de cartographie centré sur le **Cameroun**. Sa chaîne géographique actuelle repose sur :

- **Nominatim** (absent du code, référencé comme cible) pour le geocoding
- **Overpass API** (`services/places/app/overpass_client.py`) pour l'extraction de POI
- **OSRM** (`services/routing/app/osrm_client.py`) pour le routing véhicule
- **Valhalla** (`services/routing/app/valhalla_client.py`) comme moteur principal (OSRM en fallback)

TomTom apporte deux choses que ces sources OSM ne fournissent pas nativement :

1. **Couverture des adresses informelles** : au Cameroun, une proportion importante de lieux n'a pas d'adresse OSM formelle. TomTom intègre ses propres données commerciales (Points d'Intérêt, adresses postales, noms de lieux) qui peuvent compléter la couverture OSM.
2. **Trafic temps réel** : OSRM et Valhalla (en configuration locale) calculent des routes sur un graphe statique. TomTom propose un graphe routier enrichi par des données de trafic live.

La question n'est pas « TomTom est-il meilleur que Nominatim/OSRM ? » mais :

> **TomTom couvre-t-il mieux les cas géographiques réels de MAPNET au Cameroun, à quel coût, et vaut-il d'être un provider secondaire dans l'abstraction existante ?**

### 1.3 Ce que TomTom N'est PAS pour MAPNET

- **TomTom n'est pas le map-engine de MAPNET.** Le cœur cartographique de MAPNET est PostGIS + les données Overture/OSM + les tables `mapnet_divisions`, `mapnet_buildings`, `mapnet_edges`. Ce n'est pas négociable.
- **TomTom n'est pas un remplacement de Nominatim.** C'est un provider *corollaire* — il coexiste derrière la même abstraction.
- **TomTom n'est pas un remplacement de Valhalla/OSRM.** Même logique.
- **TomTom Map Display API (Orbis) n'est pas intégrable maintenant.** Cette API est marquée *Public Preview* en 2026. Elle ne peut pas être la base d'une architecture de production.

---

## 2. Ce que TomTom est — et ce qu'il n'est pas pour MAPNET

```
                        MAPNET
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    GeocodingService  RoutingService  TrafficService
           │               │               │
    ┌──────┴──────┐  ┌─────┴──────┐       │ (future)
    │             │  │            │        │
 Overpass     TomTom  Valhalla  TomTom    TomTom
 (Nominatim)          OSRM               Traffic
    │             │      │        │
    └──────┬──────┘  └───┬────────┘
           │             │
     Contrat MAPNET  Contrat MAPNET
      GeoResult        Route
           │             │
           └──────┬──────┘
                  │
           MAPNET Response
```

**La règle architecturale fondamentale :**

```
MAPNET possède ses contrats internes.
TomTom est un fournisseur de données derrière ces contrats.
Le reste de MAPNET ne sait pas quel provider est actif.
```

---

## 3. Analyse critique du document précédent

### 3.1 Ce qui était correct

| Point                              | Évaluation |
|------------------------------------|------------|
| Ajouter TomTom comme provider      | ✅ Correct  |
| Conserver Nominatim/OSRM/Valhalla  | ✅ Correct  |
| Abstraction `RoutingManager`       | ✅ Bonne direction, à pousser plus loin |
| TomTom routing avec trafic         | ✅ Premier cas d'usage pertinent |
| Fallback provider en cas d'échec   | ✅ Nécessaire, mais à redéfinir sémantiquement |

### 3.2 Ce qui était incorrect ou prématuré

**A. Normaliser vers le format OSRM**

Le document proposait :

```python
# Normalize to OSRM format
return {"code": "Ok", "routes": [...]}
```

C'est une erreur architecturale. Elle transforme implicitement OSRM en contrat interne de MAPNET. La normalisation doit se faire vers un **modèle MAPNET**, pas vers OSRM.

```
CORRECT :
  TomTom ──→ MapNet Route Model
  OSRM    ──→ MapNet Route Model
  Valhalla ──→ MapNet Route Model

INCORRECT :
  TomTom ──→ OSRM format ──→ MapNet
```

**B. Fallback aveugle**

Le document proposait :

```python
except Exception:
    fallback()
```

Un timeout TomTom ne signifie pas qu'OSRM peut fournir le même service. TomTom inclut des données de trafic qu'OSRM local n'a pas. Il faut distinguer :

- `provider_failure` : le provider est indisponible → fallback autorisé
- `provider_substitution` : le provider répond différemment → le client doit être informé

La réponse doit inclure :

```json
{
  "provider": "tomtom",
  "fallback_used": true,
  "fallback_provider": "valhalla",
  "traffic": false,
  "data_freshness": "static"
}
```

**C. Remplacer le map-engine par TomTom**

Le document suggérait d'intégrer TomTom Map Display API au cœur de MAPNET. C'est hors scope. Le map-engine MAPNET repose sur PostGIS + géométries propres + tables `mapnet_edges`, `mapnet_buildings`, `mapnet_divisions`. Cette couche est la valeur propre de MAPNET.

**D. AWS Secrets Manager**

Prématuré pour ce contexte. La clé TomTom doit être injectée via la variable d'environnement `TOMTOM_API_KEY` dans le conteneur. Gestion de secrets avancée à prévoir ultérieurement si l'infrastructure l'impose.

**E. Chiffres non vérifiés présentés comme des faits**

Ces valeurs figuraient dans le document sans source vérifiable :

- 2 500 requêtes/jour (quota free tier)
- $5–10 / 1000 requêtes
- $3–5k/mois en production
- +30 % qualité de route
- +400 % coût
- 99.95 % SLA
- données TomTom mises à jour quotidiennement vs OSM hebdomadaire

**Ces chiffres sont `TBD` jusqu'à vérification directe dans le compte/portail TomTom et les conditions commerciales actuelles.** Ils ne doivent pas entrer dans une décision d'architecture tant qu'ils ne sont pas confirmés pour la région, le type d'API, le volume et les conditions contractuelles actuelles.

**F. Code prototype proposé comme production**

```python
resp = requests.get(url, params=params)
resp.raise_for_status()
```

Il manque au minimum : timeout explicite, retry avec backoff, gestion 429, gestion 5xx, circuit breaker, logging structuré, métriques, request ID, séparation des erreurs retriables vs non-retriables.

---

## 4. Architecture cible MAPNET avec TomTom

### 4.1 services/places — état actuel

Fichiers existants :

```
services/places/app/
├── __init__.py
├── main.py            ← FastAPI, endpoints /search /nearby /reverse /geocode
└── overpass_client.py ← client Overpass API (extraction POI OSM)
```

Points d'accroche pour TomTom :

- `main.py` expose `/api/v1/places/search` → recherche textuelle sur PostGIS
- `main.py` expose `/api/v1/places/nearest-district` → reverse geocoding sur `mapnet_divisions`
- `overpass_client.py` → client Overpass pour scraping POI

TomTom vient s'ajouter **en parallèle** d'Overpass, derrière une interface commune.

### 4.2 services/routing — état actuel

Fichiers existants :

```
services/routing/app/
├── __init__.py
├── main.py            ← FastAPI, endpoints /route /navigate /alternatives /map-match
├── osrm_client.py     ← client OSRM (routing véhicule, map matching)
└── valhalla_client.py ← client Valhalla (routing principal, trace attributes)
```

Architecture actuelle :

```
main.py
  │
  ├── engine=auto  →  Valhalla (prioritaire) → OSRM (fallback)
  ├── engine=valhalla → Valhalla uniquement
  └── engine=osrm    → OSRM uniquement
```

TomTom vient s'ajouter comme troisième engine (`engine=tomtom`), derrière la même interface.

### 4.3 Structure cible après intégration TomTom

```
services/places/app/
├── __init__.py
├── main.py
├── overpass_client.py          ← existant, inchangé
├── providers/
│   ├── __init__.py
│   ├── base.py                 ← GeocodingProvider (ABC)
│   ├── nominatim.py            ← NominatimProvider (wraps Nominatim/Overpass)
│   └── tomtom.py               ← TomTomGeocodingProvider (NOUVEAU)
├── domain/
│   ├── __init__.py
│   ├── geo_result.py           ← GeoResult (contrat MAPNET)
│   └── address.py              ← Address (contrat MAPNET)
└── geocoder.py                 ← GeocodingService (orchestre les providers)

services/routing/app/
├── __init__.py
├── main.py
├── osrm_client.py              ← existant, inchangé
├── valhalla_client.py          ← existant, inchangé
├── providers/
│   ├── __init__.py
│   ├── base.py                 ← RoutingProvider (ABC)
│   ├── osrm.py                 ← OSRMProvider (wraps osrm_client.py)
│   ├── valhalla.py             ← ValhallaProvider (wraps valhalla_client.py)
│   └── tomtom.py               ← TomTomRoutingProvider (NOUVEAU)
├── domain/
│   ├── __init__.py
│   └── route.py                ← Route, Step, ProviderMeta (contrat MAPNET)
└── router.py                   ← RoutingService (orchestre les providers)
```

---

## 5. Spec — Phase 0 : TomTomProvider corollaire de Nominatim

### 5.1 Périmètre

**Objectif unique :** Introduire `TomTomGeocodingProvider` dans `services/places` sans modifier le comportement existant. Les endpoints `/api/v1/places/search`, `/api/v1/places/nearby`, `/api/v1/places/nearest-district` restent inchangés pour les clients.

**Ce qui N'est PAS dans ce périmètre :**
- Modifier `main.py` au-delà de l'injection du provider
- Remplacer Overpass ou la recherche PostGIS existante
- Exposer de nouveaux endpoints publics (sauf `/api/v1/places/geocode` si absent)
- Toucher au routing
- Modifier le schéma de base de données

### 5.2 Contrat MAPNET — `domain/geo_result.py`

```python
# services/places/app/domain/geo_result.py
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Address:
    """Adresse normalisée au format MAPNET, indépendante du provider."""
    display_name: str
    street: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    postcode: Optional[str] = None


@dataclass
class GeoResult:
    """Résultat géographique normalisé MAPNET.

    provider_confidence : score brut renvoyé par le provider (0.0–1.0), si disponible.
    mapnet_confidence   : score calculé par MAPNET (0.0–1.0), toujours présent.
    Les deux ne sont PAS comparables entre providers.
    """
    latitude: float
    longitude: float
    address: Address
    provider: str                          # "nominatim" | "tomtom" | "overpass"
    provider_confidence: Optional[float] = None
    mapnet_confidence: float = 0.0
    distance_m: Optional[float] = None
    source_id: Optional[str] = None        # identifiant interne du provider
    raw: Optional[dict] = field(default=None, repr=False)  # réponse brute, non exposée
```

> **Important :** `provider_confidence` est la valeur brute du provider. `mapnet_confidence` est calculée par MAPNET selon ses propres critères. Ces deux valeurs ne doivent jamais être comparées directement entre Nominatim et TomTom — leurs échelles sont différentes.

### 5.3 Interface provider — `providers/base.py`

```python
# services/places/app/providers/base.py
from abc import ABC, abstractmethod
from typing import List, Optional
from ..domain.geo_result import GeoResult


class GeocodingProvider(ABC):
    """Contrat commun pour tous les providers de geocoding MAPNET."""

    name: str  # identifiant du provider, ex: "nominatim", "tomtom"

    @abstractmethod
    def geocode(self, query: str, limit: int = 5,
                lat: Optional[float] = None,
                lon: Optional[float] = None) -> List[GeoResult]:
        """Transforme une requête textuelle en liste de GeoResult MAPNET."""
        ...

    @abstractmethod
    def reverse_geocode(self, lat: float, lon: float) -> Optional[GeoResult]:
        """Transforme des coordonnées en GeoResult MAPNET."""
        ...
```

### 5.4 TomTomGeocodingProvider — `providers/tomtom.py`

```python
# services/places/app/providers/tomtom.py
"""
Provider TomTom pour le geocoding et le reverse geocoding MAPNET.

Ce module est le SEUL endroit de MAPNET qui connaît les détails de l'API TomTom.
Il normalise les réponses TomTom vers le contrat GeoResult défini dans domain/.

NOTE AUTHENTIFICATION : le provider utilise le paramètre query `key=` pour
l'authentification. TomTom Search v2 accepte également un header
`TomTom-Api-Key` sur certains endpoints — à vérifier dans la documentation
officielle pour l'endpoint exact utilisé avant de modifier ce mécanisme.
Ne pas changer le mode d'auth sans validation contre l'API réelle.
"""
import logging
import os
from typing import List, Optional
from urllib.parse import quote

import httpx

from .base import GeocodingProvider
from ..domain.geo_result import Address, GeoResult
from ..errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderTemporaryUnavailable,
    ProviderNoResult,
    ProviderResponseError,
)

logger = logging.getLogger(__name__)

TOMTOM_API_BASE = "https://api.tomtom.com"
TOMTOM_SEARCH_VERSION = 2
# Biaisage géographique vers le Cameroun (bbox approximative)
_CAMEROON_COUNTRYCODE = "CMR"


class TomTomGeocodingProvider(GeocodingProvider):
    """Provider TomTom corollaire à NominatimProvider dans MAPNET.

    Utilise l'API TomTom Search v2 pour :
      - geocoding (fuzzy search)
      - reverse geocoding

    Ne gère PAS le scraping de POI (c'est le rôle d'overpass_client.py).
    Ne gère PAS la recherche textuelle sur PostGIS (c'est le rôle de main.py).

    Le client HTTP (httpx.Client) est créé une fois à l'initialisation et
    réutilisé pour toutes les requêtes. Appeler close() en fin de vie ou
    utiliser le provider comme context manager.
    """

    name = "tomtom"

    def __init__(self, api_key: Optional[str] = None,
                 timeout: float = 10.0, max_retries: int = 2):
        self._api_key = api_key or os.environ.get("TOMTOM_API_KEY", "")
        if not self._api_key:
            raise ProviderAuthError("TOMTOM_API_KEY non définie")
        self._timeout = timeout
        self._max_retries = max_retries
        # Client réutilisable : évite de recréer la connexion TCP à chaque appel.
        self._client = httpx.Client(timeout=self._timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------ #
    # Interface publique                                                    #
    # ------------------------------------------------------------------ #

    def geocode(self, query: str, limit: int = 5,
                lat: Optional[float] = None,
                lon: Optional[float] = None) -> List[GeoResult]:
        """Geocoding TomTom : texte → liste de GeoResult MAPNET.

        La requête est encodée avec urllib.parse.quote (RFC 3986) avant
        d'être insérée dans le chemin URL — httpx.URL() ne doit pas être
        utilisé comme mécanisme d'encodage de chemin.
        """
        encoded_query = quote(query, safe="")
        url = (f"{TOMTOM_API_BASE}/search/{TOMTOM_SEARCH_VERSION}"
               f"/search/{encoded_query}.json")
        params = {
            "key": self._api_key,
            "limit": limit,
            "language": "fr-FR",
            "countrySet": _CAMEROON_COUNTRYCODE,
        }
        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon

        data = self._get(url, params)
        return [self._to_geo_result(r) for r in data.get("results", [])]

    def reverse_geocode(self, lat: float, lon: float) -> Optional[GeoResult]:
        """Reverse geocoding TomTom : coordonnées → GeoResult MAPNET."""
        url = (f"{TOMTOM_API_BASE}/search/{TOMTOM_SEARCH_VERSION}"
               f"/reverseGeocode/{lat},{lon}.json")
        params = {
            "key": self._api_key,
            "language": "fr-FR",
        }
        data = self._get(url, params)
        addresses = data.get("addresses", [])
        if not addresses:
            raise ProviderNoResult(
                f"TomTom reverse geocode: aucun résultat pour {lat},{lon}"
            )
        return self._to_geo_result_reverse(addresses[0])

    # ------------------------------------------------------------------ #
    # Normalisation TomTom → GeoResult MAPNET                              #
    # ------------------------------------------------------------------ #

    def _to_geo_result(self, item: dict) -> GeoResult:
        """Normalise un résultat TomTom Search vers GeoResult MAPNET."""
        pos = item.get("position", {})
        if not isinstance(pos, dict):
            raise ProviderResponseError(
                f"TomTom: champ 'position' inattendu: {type(pos)}"
            )
        addr = item.get("address", {})
        score = item.get("score")  # score brut TomTom, non comparable à Nominatim

        mapnet_address = Address(
            display_name=addr.get("freeformAddress", ""),
            street=addr.get("streetName"),
            city=addr.get("localName") or addr.get("municipality"),
            region=addr.get("countrySubdivision"),
            country=addr.get("country"),
            postcode=addr.get("postalCode"),
        )

        return GeoResult(
            latitude=float(pos.get("lat", 0.0)),
            longitude=float(pos.get("lon", 0.0)),
            address=mapnet_address,
            provider=self.name,
            provider_confidence=float(score) if score is not None else None,
            mapnet_confidence=self._compute_mapnet_confidence(item),
            source_id=item.get("id"),
            raw=item,  # non exposé dans les réponses API MAPNET
        )

    def _to_geo_result_reverse(self, item: dict) -> GeoResult:
        """Normalise un résultat TomTom ReverseGeocode vers GeoResult MAPNET.

        La structure réelle de la réponse reverse geocode TomTom est :
          { "position": "lat,lon", "address": {...} }
        Le champ position est une chaîne "lat,lon", pas un dict.
        Parsing défensif : si la structure est différente de ce qui est attendu,
        lever ProviderResponseError plutôt que retourner 0.0,0.0 silencieusement.
        """
        addr = item.get("address", {})

        pos_raw = item.get("position", "")
        try:
            if isinstance(pos_raw, dict):
                # Certaines versions de l'API retournent un dict {lat, lon}
                rlat = float(pos_raw["lat"])
                rlon = float(pos_raw["lon"])
            elif isinstance(pos_raw, str) and pos_raw:
                parts = pos_raw.split(",")
                if len(parts) != 2:
                    raise ValueError(f"format inattendu: '{pos_raw}'")
                rlat = float(parts[0].strip())
                rlon = float(parts[1].strip())
            else:
                raise ValueError(f"type inattendu: {type(pos_raw)}")
        except (ValueError, KeyError) as exc:
            raise ProviderResponseError(
                f"TomTom reverse geocode: impossible de parser 'position': {exc}"
            ) from exc

        mapnet_address = Address(
            display_name=addr.get("freeformAddress", ""),
            street=addr.get("streetName"),
            city=addr.get("localName") or addr.get("municipality"),
            region=addr.get("countrySubdivision"),
            country=addr.get("country"),
            postcode=addr.get("postalCode"),
        )

        return GeoResult(
            latitude=rlat,
            longitude=rlon,
            address=mapnet_address,
            provider=self.name,
            provider_confidence=None,  # TomTom reverse geocode ne fournit pas de score
            mapnet_confidence=self._compute_mapnet_confidence_reverse(item),
            source_id=None,
            raw=item,
        )

    def _compute_mapnet_confidence(self, item: dict) -> float:
        """Heuristique MAPNET de confiance — NON CALIBRÉE.

        ATTENTION : ces coefficients (0.90, 0.80, etc.) sont des estimations
        initiales basées sur la sémantique des types TomTom. Ils ne sont PAS
        calibrés sur des données réelles et ne doivent PAS être utilisés pour
        comparer TomTom à Nominatim dans le benchmark.

        Le benchmark (§7) utilisera `result_found`, `lat_ok`, `address_complete`
        comme critères objectifs. `mapnet_confidence` sera recalibrée après
        le benchmark si TomTom est retenu.
        """
        entity_type = item.get("entityType", "")
        addr = item.get("address", {})

        # Heuristique de type — à recalibrer après benchmark
        type_scores = {
            "PointAddress":          0.90,  # adresse précise
            "AddressRange":          0.70,  # plage d'adresses
            "Street":                0.60,  # rue sans numéro
            "Municipality":          0.55,  # ville/commune
            "MunicipalitySubdivision": 0.65, # quartier/arrondissement
            "POI":                   0.80,  # point d'intérêt nommé
            "Country":               0.30,  # pays seulement
        }
        score = type_scores.get(entity_type, 0.50)

        # Bonus si adresse complète (rue + ville) — heuristique, non calibré
        if addr.get("streetName") and addr.get("localName"):
            score = min(score + 0.05, 1.0)

        # Bonus si résultat au Cameroun — heuristique, non calibré
        if addr.get("countryCode") in ("CM", "CMR"):
            score = min(score + 0.05, 1.0)

        return round(score, 2)

    def _compute_mapnet_confidence_reverse(self, item: dict) -> float:
        """Heuristique MAPNET reverse geocode — NON CALIBRÉE (voir ci-dessus)."""
        addr = item.get("address", {})
        score = 0.60
        if addr.get("streetName"):
            score += 0.15
        if addr.get("postalCode"):
            score += 0.05
        return round(min(score, 1.0), 2)

    # ------------------------------------------------------------------ #
    # HTTP avec gestion d'erreurs                                          #
    # ------------------------------------------------------------------ #

    def _get(self, url: str, params: dict) -> dict:
        """GET avec timeout, retry contrôlé et classification des erreurs.

        Erreurs non retriables (levées immédiatement) :
          - ProviderAuthError  : 401/403
          - ProviderRateLimitError : 429

        Erreurs retriables avec backoff minimal :
          - ProviderTemporaryUnavailable : 5xx
          - ProviderTimeoutError : timeout réseau

        Les messages d'erreur internes (codes HTTP, détails API) ne doivent
        pas être exposés tels quels dans les réponses FastAPI — voir §5.6.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                r = self._client.get(url, params=params)
                if r.status_code in (401, 403):
                    raise ProviderAuthError(
                        f"TomTom: clé API invalide ou non autorisée ({r.status_code})"
                    )
                if r.status_code == 429:
                    raise ProviderRateLimitError("TomTom: quota atteint (429)")
                if r.status_code >= 500:
                    if attempt < self._max_retries:
                        logger.warning(
                            "TomTom %s: tentative %d/%d",
                            r.status_code, attempt + 1, self._max_retries + 1,
                        )
                        continue
                    raise ProviderTemporaryUnavailable(
                        f"TomTom: service indisponible ({r.status_code})"
                    )
                r.raise_for_status()
                return r.json()
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    logger.warning(
                        "TomTom timeout: tentative %d/%d",
                        attempt + 1, self._max_retries + 1,
                    )
                    continue
                raise ProviderTimeoutError(
                    f"TomTom timeout après {self._max_retries + 1} tentatives"
                ) from exc
            except (ProviderAuthError, ProviderRateLimitError):
                raise  # ne jamais retry ces erreurs
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    continue
                raise
        raise last_exc  # type: ignore
```

### 5.5 Modèle d'erreur — `errors.py`

```python
# services/places/app/errors.py
"""Hiérarchie d'erreurs provider pour MAPNET.

Utilisée par tous les providers géographiques (geocoding ET routing).
Les messages d'erreur internes (codes HTTP TomTom, stack traces) ne doivent
jamais être exposés directement dans les réponses HTTP FastAPI.
Le handler FastAPI doit intercepter ProviderError et retourner un message
générique au client, tout en loggant le détail en interne.
"""


class ProviderError(Exception):
    """Erreur base pour tout provider géographique MAPNET."""


class ProviderAuthError(ProviderError):
    """401/403 — ne pas retry, désactiver le provider."""


class ProviderRateLimitError(ProviderError):
    """429 — backoff / gestion de quota."""


class ProviderTimeoutError(ProviderError):
    """Timeout réseau — retry contrôlé possible."""


class ProviderTemporaryUnavailable(ProviderError):
    """5xx — retry contrôlé possible, ne pas substituer silencieusement."""


class ProviderNoResult(ProviderError):
    """Le provider a répondu mais n'a aucun résultat."""


class ProviderResponseError(ProviderError):
    """Le provider a renvoyé une réponse inattendue ou malformée."""
```

### 5.6 Point d'injection dans `main.py`

Le provider TomTom s'injecte dans les endpoints existants **sans modifier leurs signatures**. Exemple pour un futur endpoint `/api/v1/places/geocode` :

```python
# Dans services/places/app/main.py
# Ajout minimal — le reste de main.py est inchangé

from .providers.tomtom import TomTomGeocodingProvider
from .errors import ProviderError, ProviderNoResult

_tomtom_provider: Optional[TomTomGeocodingProvider] = None

def _get_tomtom() -> Optional[TomTomGeocodingProvider]:
    global _tomtom_provider
    if _tomtom_provider is None:
        try:
            _tomtom_provider = TomTomGeocodingProvider()
        except Exception:
            return None  # TomTom optionnel — MAPNET fonctionne sans lui
    return _tomtom_provider


@app.get("/api/v1/places/geocode")
def geocode(q: str, lat: Optional[float] = None, lon: Optional[float] = None,
            provider: str = "auto"):
    """
    Geocoding MAPNET.

    provider=auto : TomTom si disponible, sinon résultat PostGIS local.
    provider=tomtom : TomTom uniquement.
    provider=local : PostGIS uniquement (comportement actuel de /search).
    """
    provider = (provider or "auto").lower()
    tomtom = _get_tomtom()

    if provider in ("auto", "tomtom") and tomtom is not None:
        try:
            results = tomtom.geocode(q, lat=lat, lon=lon)
            return {
                "status": "ok",
                "provider": "tomtom",
                "fallback_used": False,
                "results": [_geo_result_to_dict(r) for r in results],
            }
        except ProviderNoResult:
            if provider == "tomtom":
                return {"status": "ok", "provider": "tomtom", "results": []}
            # provider=auto → continuer vers PostGIS
        except ProviderError as exc:
            logger.warning("TomTom geocode échoué: %s — repli PostGIS", exc)
            if provider == "tomtom":
                raise HTTPException(status_code=502, detail=str(exc))
            # provider=auto → continuer vers PostGIS

    # Repli PostGIS (appel interne à search_places)
    return {
        **search_places(q=q, lat=lat, lon=lon),
        "provider": "local",
        "fallback_used": provider == "auto" and tomtom is not None,
    }
```

---

## 6. Spec — Phase 1 : TomTomProvider routing corollaire de OSRM/Valhalla

### 6.1 Périmètre

**Objectif unique :** Introduire `TomTomRoutingProvider` dans `services/routing` sans modifier les endpoints existants. L'engine `tomtom` s'ajoute aux options `auto`, `valhalla`, `osrm` existantes dans `main.py`.

### 6.2 Contrat MAPNET — `domain/route.py`

```python
# services/routing/app/domain/route.py
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProviderMeta:
    """Méta-information sur le provider utilisé pour cette route.
    Exposée dans la réponse API pour transparence client.
    """
    provider: str                          # "osrm" | "valhalla" | "tomtom"
    fallback_used: bool = False
    fallback_provider: Optional[str] = None
    traffic: bool = False                  # True si la route intègre du trafic live
    data_freshness: str = "static"         # "static" | "realtime"


@dataclass
class Step:
    instruction: str
    maneuver: str
    modifier: str
    location: List[float]                  # [lon, lat]
    distance: float
    duration: float
    name: str = ""


@dataclass
class Route:
    """Route normalisée MAPNET. Indépendante du provider."""
    distance: float                        # mètres
    duration: float                        # secondes
    geometry: dict                         # GeoJSON LineString
    steps: List[Step] = field(default_factory=list)
    provider_meta: Optional[ProviderMeta] = None
    badges: dict = field(default_factory=dict)  # secondary_m, unpaved_m, etc.
```

### 6.3 Interface provider — `providers/base.py`

```python
# services/routing/app/providers/base.py
from abc import ABC, abstractmethod
from typing import List, Optional
from ..domain.route import Route


class RoutingProvider(ABC):
    name: str

    @abstractmethod
    def route(self, from_lat: float, from_lon: float,
              to_lat: float, to_lon: float,
              costing: str = "auto") -> Route:
        """Calcule un itinéraire et retourne un Route MAPNET."""
        ...

    @abstractmethod
    def available(self) -> bool:
        """Retourne True si le provider est accessible."""
        ...
```

### 6.4 TomTomRoutingProvider — `providers/tomtom.py`

```python
# services/routing/app/providers/tomtom.py
"""
Provider TomTom pour le routing MAPNET.
Ce module est le SEUL endroit qui connaît l'API TomTom Routing.
Il normalise les réponses vers le contrat Route MAPNET — jamais vers OSRM.

Réutilise la hiérarchie ProviderError de services/places/app/errors.py.
Pour le routing, cette hiérarchie doit être extraite dans un package partagé
ou dupliquée dans services/routing/app/errors.py avec les mêmes noms.
"""
import logging
import os
from typing import List, Optional

import httpx

from .base import RoutingProvider
from ..domain.route import ProviderMeta, Route, Step
from ..errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderTemporaryUnavailable,
    ProviderNoResult,
    ProviderResponseError,
)

logger = logging.getLogger(__name__)

TOMTOM_ROUTING_BASE = "https://api.tomtom.com/routing/1"

_COSTING_MAP = {
    "auto":       "car",
    "car":        "car",
    "motorcycle": "motorcycle",
    "bicycle":    "bicycle",
    "pedestrian": "pedestrian",
    "foot":       "pedestrian",
}


class TomTomRoutingProvider(RoutingProvider):
    """Provider TomTom routing, corollaire de ValhallaProvider et OSRMProvider.

    Avantage principal sur OSRM/Valhalla local : intègre les données de trafic
    live TomTom dans le calcul d'itinéraire.
    La réponse est normalisée vers Route MAPNET — jamais vers le format OSRM.

    NOTE LIMITES : les throttles (QPS, quota journalier) dépendent du type de
    clé et du contrat TomTom. Ne pas coder de limite en dur — les configurer
    via des variables d'environnement si un rate limiter est nécessaire.
    """

    name = "tomtom"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0):
        self._api_key = api_key or os.environ.get("TOMTOM_API_KEY", "")
        self._timeout = timeout
        self._client = httpx.Client(timeout=self._timeout)

    def close(self) -> None:
        self._client.close()

    def available(self) -> bool:
        return bool(self._api_key)

    def route(self, from_lat: float, from_lon: float,
              to_lat: float, to_lon: float,
              costing: str = "auto") -> Route:
        """Calcule un itinéraire TomTom et retourne un Route MAPNET."""
        tt_vehicle = _COSTING_MAP.get(costing, "car")
        url = (f"{TOMTOM_ROUTING_BASE}/calculateRoute/"
               f"{from_lat},{from_lon}:{to_lat},{to_lon}/json")
        params = {
            "key": self._api_key,
            "travelMode": tt_vehicle,
            "routeRepresentation": "polyline",
            "computeTravelTimeFor": "all",
            "traffic": "true",
            "language": "fr-FR",
            "instructionsType": "text",
        }

        try:
            r = self._client.get(url, params=params)
            if r.status_code in (401, 403):
                raise ProviderAuthError(
                    f"TomTom routing: clé invalide ({r.status_code})"
                )
            if r.status_code == 429:
                raise ProviderRateLimitError("TomTom routing: quota atteint (429)")
            if r.status_code >= 500:
                raise ProviderTemporaryUnavailable(
                    f"TomTom routing: service indisponible ({r.status_code})"
                )
            r.raise_for_status()
            data = r.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("TomTom routing timeout") from exc
        except (ProviderAuthError, ProviderRateLimitError,
                ProviderTemporaryUnavailable, ProviderTimeoutError):
            raise

        return self._normalize(data, costing)

    # ------------------------------------------------------------------ #
    # Normalisation TomTom → Route MAPNET                                  #
    # NE PAS normaliser vers OSRM format.                                  #
    # ------------------------------------------------------------------ #

    def _normalize(self, data: dict, costing: str) -> Route:
        routes = data.get("routes", [])
        if not routes:
            raise ProviderNoResult("TomTom routing: aucune route retournée")

        rt = routes[0]
        summary = rt.get("summary", {})
        legs = rt.get("legs", [])
        instructions = rt.get("guidance", {}).get("instructions", [])

        # Géométrie GeoJSON LineString depuis les points de chaque leg
        coords = []
        for leg in legs:
            for pt in leg.get("points", []):
                coords.append([
                    float(pt.get("longitude", 0.0)),
                    float(pt.get("latitude", 0.0)),
                ])
        geometry = {"type": "LineString", "coordinates": coords}

        # Steps depuis les instructions de guidage TomTom
        steps = []
        for instr in instructions:
            pt = instr.get("point", {}) or {}
            steps.append(Step(
                instruction=instr.get("message", ""),
                maneuver=instr.get("maneuverType", ""),
                modifier="",
                location=[
                    float(pt.get("longitude", 0.0)),
                    float(pt.get("latitude", 0.0)),
                ],
                distance=float(instr.get("routeOffsetInMeters", 0.0)),
                duration=float(instr.get("travelTimeInSeconds", 0.0)),
                name=instr.get("street", ""),
            ))

        provider_meta = ProviderMeta(
            provider=self.name,
            fallback_used=False,
            traffic=True,           # TomTom routing intègre toujours le trafic si disponible
            data_freshness="realtime",
        )

        return Route(
            distance=float(summary.get("lengthInMeters", 0.0)),
            duration=float(summary.get("travelTimeInSeconds", 0.0)),
            geometry=geometry,
            steps=steps,
            provider_meta=provider_meta,
        )
```

### 6.5 Point d'injection dans `main.py` (routing)

```python
# Dans services/routing/app/main.py
# Modification minimale — ajouter engine=tomtom

from .providers.tomtom import TomTomRoutingProvider

_tomtom_routing: Optional[TomTomRoutingProvider] = None

def _get_tomtom_routing() -> Optional[TomTomRoutingProvider]:
    global _tomtom_routing
    if _tomtom_routing is None:
        provider = TomTomRoutingProvider()
        if provider.available():
            _tomtom_routing = provider
    return _tomtom_routing

# Dans calculate_route() — ajouter le cas engine=tomtom :
#
# if engine in ("auto", "tomtom"):
#     tomtom = _get_tomtom_routing()
#     if tomtom:
#         try:
#             r = tomtom.route(from_lat, from_lon, to_lat, to_lon, costing)
#             return {
#                 "status": "ok",
#                 "engine": "tomtom",
#                 "traffic": True,
#                 "data_freshness": "realtime",
#                 "routes": [_route_to_dict(r)],
#             }
#         except Exception as exc:
#             logger.warning("TomTom routing échoué: %s", exc)
#             if engine == "tomtom":
#                 raise HTTPException(502, detail=str(exc))
#             # engine=auto → continuer vers Valhalla
```

---

## 7. Benchmark Cameroun : corpus et méthode

### 7.1 Pourquoi ce benchmark est obligatoire avant toute décision

Les chiffres comme « +30 % qualité », « données mises à jour quotidiennement » ou « $X/1000 requêtes » ne doivent pas entrer dans une décision architecture tant qu'ils ne sont pas vérifiés sur les cas réels de MAPNET. Le benchmark est la source de vérité.

### 7.2 Corpus de test — structure par axes expérimentaux

Le corpus n'est pas une simple liste de 230 requêtes. Il est structuré par **axes expérimentaux** pour permettre une analyse différenciée après le benchmark : on ne veut pas seulement « TomTom : 72 % / Nominatim : 61 % » — on veut savoir **sur quels axes l'écart existe**.

```
CORPUS CAMEROUN
│
├── Axe géographique
│   ├── urbain_yaounde    (40 requêtes)
│   ├── urbain_douala     (40 requêtes)
│   ├── secondaire        (30 requêtes) ← Bafoussam, Bamenda, Kribi, Limbe
│   └── rural             (30 requêtes) ← Ntui, Bafia, zones hors grands axes
│
├── Axe linguistique
│   ├── francophone       (requêtes en français)
│   └── anglophone        (requêtes en anglais — Bamenda, Limbe, Buea)
│
├── Axe toponymique
│   ├── nom_officiel      (nom administratif standard)
│   ├── variante_ortho    (variante orthographique, accent manquant, etc.)
│   └── nom_local         (nom de quartier / repère local)
│
├── Axe type de requête
│   ├── poi               (30 requêtes) ← pharmacie, école, station, hôpital
│   ├── adresse_formelle  (20 requêtes) ← rue + numéro si disponible
│   ├── adresse_informelle(30 requêtes) ← "derrière...", "carrefour...", "entrée..."
│   └── reverse           (30 requêtes) ← lat/lon urbain + rural
│
└── Total : ~250 requêtes
    (les catégories se chevauchent : une requête peut être
     urbain_yaounde + francophone + nom_local + adresse_informelle)
```

Chaque requête porte ses axes comme tags. Exemple :

```json
{
  "query": "Université de Yaoundé I",
  "tags": ["urbain_yaounde", "francophone", "nom_officiel", "poi"],
  "ground_truth": { "lat": 3.8627, "lon": 11.5078 }
}
```

```json
{
  "query": "University of Buea",
  "tags": ["secondaire", "anglophone", "nom_officiel", "poi"],
  "ground_truth": { "lat": 4.1553, "lon": 9.2310 }
}
```

```json
{
  "query": "derrière la pharmacie du marché central Yaoundé",
  "tags": ["urbain_yaounde", "francophone", "adresse_informelle"],
  "ground_truth": null,
  "manual_evaluation": null
}
```

**Règle obligatoire : ground truth manuelle pour chaque requête.** Un résultat « non vide » n'est pas un résultat correct. La vérification se fait par coordonnées réelles (±100 m pour urbain, ±500 m pour rural).

Les requêtes avec `ground_truth: null` sont évaluées manuellement après récupération des résultats. Le résultat de cette évaluation **doit être enregistré dans le fichier corpus** (champ `manual_evaluation`) pour rester dans le calcul reproductible — voir §7.5.

### 7.3 Grille de mesure

Pour chaque requête, mesurer :

| Métrique                     | Description                                                      |
|------------------------------|------------------------------------------------------------------|
| `result_found`               | Le provider a retourné au moins un résultat (oui/non)            |
| `lat_ok` / `lon_ok`          | Coordonnées à ±100 m (urbain) / ±500 m (rural) du ground truth  |
| `address_complete`           | Rue + ville présentes dans la réponse normalisée                 |
| `city_correct`               | Ville identifiée correctement                                    |
| `region_correct`             | Région/département correct                                       |
| `response_time_ms`           | Temps de réponse en millisecondes                                |
| `provider`                   | "nominatim" | "tomtom"                                           |
| `mapnet_confidence`          | Score calculé par MAPNET (0.0–1.0)                               |
| `error`                      | Type d'erreur si aucun résultat (NoResult, Timeout, etc.)        |

### 7.4 Script de benchmark

```python
# scripts/benchmark_geocoding.py
"""
Benchmark Nominatim vs TomTom sur le corpus Cameroun.

Le benchmark est SYMÉTRIQUE : les deux providers reçoivent exactement les
mêmes requêtes dans le même ordre, avec les mêmes critères de mesure.
Ne pas comparer des résultats produits par des corpus ou des paramètres
différents.

Usage:
  TOMTOM_API_KEY=xxx python scripts/benchmark_geocoding.py \
    --corpus scripts/corpus_cameroun.json \
    --output results/benchmark_$(date +%Y%m%d).json
"""
import json
import math
import time
import argparse
import os
import sys

sys.path.insert(0, "services/places")

from app.providers.tomtom import TomTomGeocodingProvider
from app.providers.nominatim import NominatimProvider  # à implémenter en Phase 0
from app.errors import ProviderError

NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres entre deux points."""
    R = 6_371_000.0
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def run_benchmark(corpus_path: str, output_path: str) -> None:
    with open(corpus_path) as f:
        corpus = json.load(f)

    providers = [
        ("tomtom",    TomTomGeocodingProvider()),
        ("nominatim", NominatimProvider(base_url=NOMINATIM_URL)),
    ]

    results = []

    for case in corpus:
        q = case["query"]
        gt = case.get("ground_truth")           # {"lat": ..., "lon": ...} ou null
        tags = case.get("tags", [])
        manual = case.get("manual_evaluation")  # rempli après évaluation manuelle

        for provider_name, provider in providers:
            t0 = time.perf_counter()
            error = None
            geo_results = []
            http_status = None
            try:
                geo_results = provider.geocode(q)
            except ProviderError as exc:
                error = type(exc).__name__

            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
            top = geo_results[0] if geo_results else None

            # Distance au ground truth (si disponible et résultat trouvé)
            distance_gt_m = None
            lat_ok = None
            if gt and top:
                distance_gt_m = round(
                    _haversine_m(top.latitude, top.longitude,
                                 gt["lat"], gt["lon"]), 1
                )
                threshold = 100.0 if "urbain" in tags else 500.0
                lat_ok = distance_gt_m <= threshold

            results.append({
                "query":            q,
                "tags":             tags,
                "provider":         provider_name,
                "result_found":     top is not None,
                "lat":              top.latitude if top else None,
                "lon":              top.longitude if top else None,
                "address_display":  top.address.display_name if top else None,
                "city":             top.address.city if top else None,
                "address_complete": bool(
                    top and top.address.street and top.address.city
                ) if top else False,
                "mapnet_confidence": top.mapnet_confidence if top else None,
                # mapnet_confidence est NON CALIBRÉ — ne pas utiliser pour comparer
                # les providers ; utiliser lat_ok, address_complete, result_found.
                "response_time_ms": elapsed_ms,
                "error":            error,
                "ground_truth":     gt,
                "distance_gt_m":    distance_gt_m,
                "lat_ok":           lat_ok,
                "manual_evaluation": manual,  # préservé depuis le corpus
            })

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Résumé console par provider et par axe
    from collections import defaultdict
    summary: dict = defaultdict(lambda: defaultdict(list))
    for r in results:
        p = r["provider"]
        summary[p]["result_found"].append(r["result_found"])
        if r["lat_ok"] is not None:
            summary[p]["lat_ok"].append(r["lat_ok"])
        if r["address_complete"] is not None:
            summary[p]["address_complete"].append(r["address_complete"])
        summary[p]["response_ms"].append(r["response_time_ms"])

    print(f"\n{'─'*55}")
    print(f"{'Métrique':<30} {'TomTom':>10} {'Nominatim':>12}")
    print(f"{'─'*55}")
    for metric in ("result_found", "lat_ok", "address_complete"):
        row = []
        for pname in ("tomtom", "nominatim"):
            vals = summary[pname][metric]
            pct = f"{100*sum(vals)/len(vals):.1f}%" if vals else "n/a"
            row.append(pct)
        print(f"{metric:<30} {row[0]:>10} {row[1]:>12}")
    for pname in ("tomtom", "nominatim"):
        ms = summary[pname]["response_ms"]
        avg = f"{sum(ms)/len(ms):.0f}ms" if ms else "n/a"
        print(f"{'latence_moy (' + pname + ')':<30} {avg:>10}")
    print(f"{'─'*55}")
    print(f"Résultats détaillés → {output_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="scripts/corpus_cameroun.json")
    parser.add_argument("--output", default="results/benchmark.json")
    args = parser.parse_args()
    run_benchmark(args.corpus, args.output)
```

### 7.5 Format du corpus

```json
[
  {
    "query": "Université de Yaoundé I",
    "tags": ["urbain_yaounde", "francophone", "nom_officiel", "poi"],
    "ground_truth": { "lat": 3.8627, "lon": 11.5078 },
    "manual_evaluation": null
  },
  {
    "query": "University of Buea",
    "tags": ["secondaire", "anglophone", "nom_officiel", "poi"],
    "ground_truth": { "lat": 4.1553, "lon": 9.2310 },
    "manual_evaluation": null
  },
  {
    "query": "Ntui",
    "tags": ["rural", "francophone", "nom_officiel"],
    "ground_truth": { "lat": 4.4545, "lon": 11.6359 },
    "manual_evaluation": null
  },
  {
    "query": "derrière la pharmacie du marché central Yaoundé",
    "tags": ["urbain_yaounde", "francophone", "adresse_informelle"],
    "ground_truth": null,
    "manual_evaluation": {
      "useful": null,
      "location_error_m": null,
      "notes": "À évaluer manuellement après récupération des résultats"
    }
  }
]
```

**Règle de remplissage `manual_evaluation` :** après exécution du benchmark, les entrées avec `ground_truth: null` doivent être évaluées manuellement et le champ `manual_evaluation` mis à jour dans le fichier corpus. Ne pas laisser ces entrées hors du calcul final — elles sont souvent les plus discriminantes (adresses informelles, toponymes locaux).

---

## 8. Modèle d'erreur requis

Les deux services (`places` et `routing`) doivent utiliser la même hiérarchie.

```
ProviderError
├── ProviderAuthError          → 401/403 — ne pas retry, désactiver le provider
├── ProviderRateLimitError     → 429 — backoff, gestion quota
├── ProviderTimeoutError       → timeout réseau — retry contrôlé
├── ProviderTemporaryUnavailable → 5xx — retry contrôlé
├── ProviderNoResult           → réponse valide mais 0 résultat
└── ProviderResponseError      → réponse malformée ou inattendue
```

**Règles de fallback par type d'erreur :**

| Erreur                       | Fallback autorisé | Action                                       |
|------------------------------|-------------------|----------------------------------------------|
| `ProviderAuthError`          | Non               | Logger ERROR, désactiver provider, alerter   |
| `ProviderRateLimitError`     | Non               | Logger WARN, backoff, ne pas substituer silencieusement |
| `ProviderTimeoutError`       | Oui (avec flag)   | `fallback_used: true` dans la réponse        |
| `ProviderTemporaryUnavailable` | Oui (avec flag) | `fallback_used: true` dans la réponse        |
| `ProviderNoResult`           | Oui (sans flag)   | Autre provider si disponible                 |
| `ProviderResponseError`      | Oui (avec flag)   | Logger WARN, `fallback_used: true`           |

---

## 9. Séquence d'implémentation recommandée

**Ne pas commencer par `main.py`.** La séquence correcte est :

```
1. Vérifier dans la doc TomTom officielle :
     - endpoint exact pour Search v2 (fuzzy search)
     - endpoint exact pour reverseGeocode
     - mécanisme d'auth accepté (param `key=` vs header `TomTom-Api-Key`)
     - limites de quota associées à la clé disponible
             ↓
2. Implémenter TomTomGeocodingProvider isolé
   (services/places/app/providers/tomtom.py)
             ↓
3. Tester manuellement avec 5–10 requêtes camerounaises :
     - Yaoundé (FR)
     - Douala (FR)
     - Bamenda / Buea (EN)
     - un toponyme local (quartier/carrefour)
     - un POI générique
     - un reverse geocode urbain
     - un reverse geocode rural
             ↓
4. Vérifier les réponses brutes (raw) et corriger le parsing si nécessaire
   (structure position, champs address, entityType effectivement présents)
             ↓
5. Tests unitaires du provider (parsing, erreurs, confidence)
             ↓
6. Implémenter NominatimProvider avec la même interface GeocodingProvider
             ↓
7. Exécuter le benchmark complet Nominatim + TomTom sur corpus_cameroun.json
             ↓
8. Analyser les résultats par axe (§7.2)
             ↓
9. Décision provider (§11)
             ↓
10. Seulement après décision : intégration dans main.py
```

**Aucune de ces étapes ne modifie `main.py`, `docker-compose.yml`, le schéma PostGIS, `osrm_client.py`, `valhalla_client.py` ou `overpass_client.py`.**

---

## 10. Ce qui ne sera PAS fait dans cette phase

Ces points sont hors scope et ne doivent pas être implémentés avant la décision issue du benchmark :

| Action                                           | Raison                                                            |
|--------------------------------------------------|-------------------------------------------------------------------|
| Remplacer Nominatim/Overpass par TomTom          | TomTom est un provider corollaire, pas un remplacement            |
| Remplacer Valhalla/OSRM par TomTom               | Même principe                                                     |
| Intégrer TomTom Map Display API (Orbis)          | Public Preview — instable pour la production                      |
| Normaliser les réponses TomTom vers format OSRM  | Crée une dette architecturale implicite                           |
| Utiliser AWS Secrets Manager pour la clé TomTom  | `TOMTOM_API_KEY` en variable d'environnement est suffisant        |
| Migrer le map-engine vers TomTom                 | Le map-engine MAPNET (PostGIS + tables propres) est la valeur propre |
| Présenter les estimations de coût comme des faits | Non vérifiées sur le compte/contrat actuel                        |
| Déployer TomTom en production avant le benchmark | Le benchmark Cameroun est obligatoire d'abord                     |

---

## 11. Fichiers concernés

### Fichiers à créer (Phase 0 — geocoding)

| Fichier                                                   | Description                                      |
|-----------------------------------------------------------|--------------------------------------------------|
| `services/places/app/domain/__init__.py`                  | Module domain                                    |
| `services/places/app/domain/geo_result.py`                | GeoResult, Address (contrat MAPNET)              |
| `services/places/app/providers/__init__.py`               | Module providers                                 |
| `services/places/app/providers/base.py`                   | GeocodingProvider (ABC)                          |
| `services/places/app/providers/tomtom.py`                 | TomTomGeocodingProvider                          |
| `services/places/app/providers/nominatim.py`              | NominatimProvider (wraps Nominatim REST API)     |
| `services/places/app/errors.py`                           | Hiérarchie ProviderError                         |
| `services/places/app/geocoder.py`                         | GeocodingService (orchestre les providers)       |
| `scripts/benchmark_geocoding.py`                          | Script de benchmark Nominatim vs TomTom          |
| `scripts/corpus_cameroun.json`                            | 230 requêtes avec ground truth                   |

### Fichiers à modifier (Phase 0 — geocoding)

| Fichier                                       | Modification                                                           |
|-----------------------------------------------|------------------------------------------------------------------------|
| `services/places/app/main.py`                 | Ajouter endpoint `/api/v1/places/geocode` + injection TomTomProvider  |
| `services/places/requirements.txt`            | Ajouter `httpx` si absent                                              |

### Fichiers à créer (Phase 1 — routing)

| Fichier                                                    | Description                                      |
|------------------------------------------------------------|--------------------------------------------------|
| `services/routing/app/domain/__init__.py`                  | Module domain                                    |
| `services/routing/app/domain/route.py`                     | Route, Step, ProviderMeta (contrat MAPNET)       |
| `services/routing/app/providers/__init__.py`               | Module providers                                 |
| `services/routing/app/providers/base.py`                   | RoutingProvider (ABC)                            |
| `services/routing/app/providers/tomtom.py`                 | TomTomRoutingProvider                            |
| `services/routing/app/providers/osrm.py`                   | OSRMProvider (wraps osrm_client.py existant)     |
| `services/routing/app/providers/valhalla.py`               | ValhallaProvider (wraps valhalla_client.py existant) |
| `services/routing/app/router.py`                           | RoutingService (orchestre les providers)         |

### Fichiers à modifier (Phase 1 — routing)

| Fichier                                       | Modification                                                           |
|-----------------------------------------------|------------------------------------------------------------------------|
| `services/routing/app/main.py`                | Ajouter `engine=tomtom` dans `calculate_route()` et `alternatives()`  |
| `services/routing/requirements.txt`           | Vérifier présence de `httpx`                                           |

### Fichiers à ne PAS modifier dans cette phase

| Fichier                                            | Raison                                                |
|----------------------------------------------------|-------------------------------------------------------|
| `services/places/app/overpass_client.py`           | Client Overpass intact                                |
| `services/routing/app/osrm_client.py`              | Client OSRM intact                                    |
| `services/routing/app/valhalla_client.py`          | Client Valhalla intact                                |
| `docker-compose.yml`                               | Ajouter `TOMTOM_API_KEY` dans les env vars uniquement |
| `.env.example`                                     | Ajouter `TOMTOM_API_KEY=` (valeur vide)               |
| Schéma base de données PostGIS                     | Aucune modification                                   |

---

## 12. Décision finale : grille d'évaluation

La décision d'utiliser TomTom en production (et dans quel rôle) sera prise après le benchmark Cameroun, sur la base de cette grille :

```
                       Nominatim    TomTom
───────────────────────────────────────────────
Urbain Yaoundé/Douala
  result_found (%)
  coordonnées correctes (%)
  adresse complète (%)
  temps réponse moyen (ms)

Rural (Ntui, Bafia, etc.)
  result_found (%)
  coordonnées correctes (%)

Adresses informelles
  result_found (%)
  résultat utile (manuel)

Reverse geocoding
  résultat correct (%)
  rue identifiée (%)

Coût estimé mensuel         TBD          TBD
  (à vérifier sur compte)
SLA déclaré                 TBD          TBD
  (à vérifier contrat)
```

**Les cases `TBD` ne sont pas des oublis : elles sont volontairement vides jusqu'à vérification directe des conditions commerciales TomTom pour la région CMR et le volume de MAPNET.**

### Scénarios de décision possibles

| Résultat benchmark                                   | Décision recommandée                                           |
|------------------------------------------------------|----------------------------------------------------------------|
| TomTom nettement meilleur en rural + coût acceptable | TomTom provider prioritaire, Nominatim en fallback             |
| TomTom meilleur en urbain, équivalent en rural       | TomTom provider secondaire pour geocoding urbain précis         |
| TomTom comparable, coût plus élevé                   | Conserver Nominatim/Overpass, TomTom optionnel pour trafic     |
| TomTom moins bon en couverture Cameroun              | Ne pas intégrer TomTom geocoding, évaluer uniquement routing   |
| TomTom routing avec trafic supérieur à Valhalla local| TomTom routing en option payante / mode premium MAPNET         |

---

*Ce document remplace tout document précédent sur l'intégration TomTom dans MAPNET.*
*Il ne doit pas être utilisé comme spec d'implémentation avant complétion du benchmark (§7).*
