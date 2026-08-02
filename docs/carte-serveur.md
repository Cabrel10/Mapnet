# Architecture MapNet Carte (Serveur Backend)

## Vue d'ensemble

**MapNet Carte** est le backend HTTP centralisé qui agrège les captures terrain de tous les agents mobiles, les persiste, et les sert via une interface cartographique interactive Leaflet. Elle implémente une **architecture DDD (Domain-Driven Design)** avec séparation nette entre présentation HTTP, logique métier, et persistance.

## Stack technologique

### Runtime & Framework
- **Python 3.10+** — Langage compilé statique, stdlib robuste
- **Stdlib `http.server`** — Serveur HTTP natif (zéro dépendance pip)

### Justification du choix "zéro dépendance"
Le serveur utilise uniquement la **bibliothèque standard Python**, pas de Flask/FastAPI/Django. Raison officielle : "démarrage instantané, aucune installation pip (ne perturbe pas l'entraînement ADAN en cours)". Cela permet au backend de s'exécuter en sandbox sans dépendances externes, crucial dans un contexte d'ADAN (Adaptive Deep Agent Network) où la reproductibilité est critique.

### Architecture générale
```
http.server (stdlib)
    ↓
Handler (classe HTTP adaptatrice)
    ↓
Container (composition root DDD)
    ├── CaptureService (application)
    ├── CaptureRepository (infrastructure)
    ├── EventBus (domaine)
    └── PluginSystem (extensibilité)
```

## Couches DDD

### 1. Présentation (HTTP)

#### Endpoints publiques

| Méthode | Route | Description | Retour |
|---------|-------|-------------|--------|
| GET | `/` | Sert `index.html` (Leaflet) | HTML 200 |
| GET | `/health` | Santé service + stats rapides | JSON 200 |
| GET | `/api/captures` | Liste JSON de toutes captures | JSON 200 |
| GET | `/api/captures.geojson` | Export FeatureCollection (pour carte) | GeoJSON 200 |
| GET | `/api/stats` | Agrégats (états, kinds, trust moyen) | JSON 200 |
| GET | `/api/plugins` | Capteurs disponibles (plugin system) | JSON 200 |
| GET | `/api/events` | 30 derniers événements de domaine | JSON 200 |
| POST | `/api/captures` | Crée capture depuis agent mobile | JSON 201 |
| POST | `/api/captures/<id>/sync` | Faire progresser capture (état machine) | JSON 200 |
| GET | `/favicon.ico` | Icône navigateur | 204 No Content |

**Codes HTTP :**
- `200` — Succès lecture/update
- `201` — Ressource créée (POST /captures)
- `204` — Pas de contenu (favicon)
- `400` — Erreur client (JSON invalide, paramètres manquants)
- `404` — Route ou ressource non trouvée
- `500` — Erreur serveur (exception non capturée)

#### Handler HTTP (`backend/presentation/server.py`)
```python
class Handler(BaseHTTPRequestHandler):
    
    def _send(code, body, ctype) → None
        # Envoie réponse brute + headers + CORS
    
    def _json(obj, code) → None
        # Encode dict en JSON UTF-8 + _send()
    
    def do_GET()
        # Routes GET : statiques, /health, /api/*
    
    def do_POST()
        # Routes POST : /api/captures, /api/captures/{id}/sync
```

**Features HTTP :**
- **CORS wildcard** : `Access-Control-Allow-Origin: *`
  - Permet requêtes cross-origin depuis navigateurs front-end
  - Prod : devrait être restrictif (domaines spécifiques)
- **Logging structuré** : `[MapNet] message`
- **Gestion erreurs** : try-except wrapper ; retourne JSON + status 500 en cas exception

#### Sérialisation HTML/JSON
- HTML statique : `index.html` sert la carte Leaflet
- JSON : tous les objets domaine ont méthode `.to_dict()` pour sérialisation
- GeoJSON : export spécial via `repo.geojson()` (RFC 7946)

### 2. Application (Orchestration)

#### Container (Composition Root)
```python
class Container:
    repo: CaptureRepository
    service: CaptureService
    devices: DeviceService
    geocoder: NominatimCache
    bus: EventBus
    plugins: PluginSystem
```

Le Container instancie et câble tous les services au démarrage. C'est le point unique d'accès pour le Handler HTTP.

#### CaptureService (Logique métier)
```python
class CaptureService:
    
    def create_capture(lat, lon, kind, label, signals) → Capture
        # Valide lat/lon ∈ [-180,180] x [-90,90]
        # Crée nouvel agrégat Capture + l'ajoute au repo
        # Émet événement domain "gps_captured"
        # Retourne l'instance
    
    def sync_capture(capture_id, via_mesh=False) → Optional[Capture]
        # Récupère capture par ID
        # Applique transition état machine (NEW → ACKNOWLEDGED → SYNCED)
        # Émet événement "synced"
        # Retourne capture ou None
    
    def stats() → Dict[str, Any]
        # Agrège captures par état, kind, trust score moyen
        # Retourne dict stats
```

**Flux création capture :**
1. POST `/api/captures` arrive avec `{"lat": 12.34, "lon": -1.56, "kind": "gps", ...}`
2. Handler parse JSON + appelle `service.create_capture(...)`
3. Service **valide** coordonnées géographiques
4. Service crée instance `Capture(GeoPoint(lat,lon), kind, state=NEW, ...)`
5. Service appelle `repo.add(capture)`
6. Service émet `DomainEvent.gps_captured(id, lat, lon, accuracy)`
7. EventBus enregistre événement
8. Retourne capture sérialisée JSON + 201

**Flux synchronisation :**
1. POST `/api/captures/{id}/sync` (agent vérifie qu'il a bien reçu)
2. Service récupère capture du repo
3. State machine : NEW → ACKNOWLEDGED (via_mesh=False) ou ACKNOWLEDGED → SYNCED (via_mesh=True)
4. Émet événement synchro
5. Retourne state actuel

### 3. Domaine (Logique purement métier)

#### Entities

**GeoPoint (Value Object)**
```python
class GeoPoint:
    lat: float  # [-90, 90]
    lon: float  # [-180, 180]
    
    def to_dict() → Dict[str, float]
```

Objet de valeur immuable représentant un point géographique. Pas d'identité ; deux GeoPoint(12.3, -1.5) sont égaux.

**Capture (Aggregate Root)**
```python
class Capture:
    capture_id: str  # UUID
    point: GeoPoint
    kind: str        # "gps", "road_condition", "poi_created"
    label: str       # description libre
    state: CaptureState  # NEW, ACKNOWLEDGED, SYNCED, FAILED
    trust_score: float   # [0, 1]
    quality: QualityReport
    signals: Dict[str, Any]  # {"accuracy_m": 5.2, ...}
    created_at: datetime
    
    def record_gps() → None  # Enregistre event GPS
    def set_quality(report: QualityReport) → None
    def to_dict() → Dict[str, Any]
```

Racine d'agrégat ; possède une identité unique `capture_id`. Encapsule la logique d'état et qualité. Point d'accès pour les modifications via methods (record_gps, set_quality) — pas mutation directe des champs.

#### Events (Domain Events)

```python
class DomainEvent:
    event_id: str
    timestamp: datetime
    aggregate_id: str  # UUID Capture
    
    def to_dict() → Dict[str, Any]

# Factory functions
DomainEvent.gps_captured(id, lat, lon, accuracy_m)
DomainEvent.road_condition_detected(id, condition, severity)
DomainEvent.poi_created(id, name, category, lat, lon)
```

Événements métier qui représentent des faits historiques. Utilisés pour :
- **Audit** : trace complète des mutations
- **Reporting** : feed `/api/events` pour monitoring
- **Event sourcing** : potentiellement rejouer l'historique

#### State Machine

```python
class CaptureState(Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    SYNCED = "synced"
    FAILED = "failed"

class CaptureStateMachine:
    def __init__(state: CaptureState)
    
    def can_transition(target: CaptureState) → bool
        # NEW → ACKNOWLEDGED (mobile -> VPS)
        # ACKNOWLEDGED → SYNCED (confirmation)
        # ANYTHING → FAILED (erreur réseau)
    
    def transition(target: CaptureState) → None
        # Valide + applique ou lève InvalidTransition
```

Graphe d'états valides pour une capture. Évite états invalides (ex: SYNCED → NEW).

#### Quality Pipeline

```python
class QualitySignals:
    """Signaux bruts depuis le terrain"""
    accuracy_m: float
    hdop: float
    vdop: float
    num_satellites: int
    
class QualityReport:
    """Évaluation de qualité"""
    score: float  # [0, 1]
    flags: List[str]  # ["low_accuracy", "poor_hdop", ...]
    
    def to_dict() → Dict

class QualityPipeline:
    """Traitement signaux → score"""
    @staticmethod
    def evaluate(signals: QualitySignals) → QualityReport
        # Logique : accuracy ≤ 10m → bon score
        #           accuracy > 30m → mauvais score
        #           HDOP > 5 → flag "poor_hdop"
        #           etc.
```

Assurance qualité : convertit signaux bruts GPS (accuracy, HDOP, satellites) en score normalisé [0,1] + flags sémantiques. Utilisé par frontend pour colorer les marqueurs.

#### Schema & Migrations

```python
def migrate_v1_to_v2(d: Dict) → Dict
    # v1 : pas d'accuracy_m, pas d'owner
    # v2 : ajoute accuracy_m=0, owner=0 par défaut
    
def rollback_v2_to_v1(d: Dict) → Dict
    # Inverse
    
def ensure_current(d: Dict) → Dict
    # Valide schéma actuellement attendu (v2)
```

Gestion d'évolution de format JSON. Crucial pour persistance snapshot.

### 4. Infrastructure (Persistance)

#### CaptureRepository (Port abstrait)
```python
class CaptureRepository(ABC):
    @abstractmethod
    def add(capture: Capture) → None
    
    @abstractmethod
    def get(capture_id: str) → Optional[Capture]
    
    @abstractmethod
    def list() → List[Capture]
    
    @abstractmethod
    def geojson() → Dict  # GeoJSON export
```

Interface ; peut être implémentée par N backends (in-memory, PostgreSQL/PostGIS, MongoDB, etc.)

#### InMemoryCaptureRepository (Implémentation)
```python
class InMemoryCaptureRepository:
    _store: Dict[str, Capture]  # clé=capture_id, valeur=instance
    _lock: threading.Lock  # thread-safety
    snapshot_path: str  # chemin fichier JSON
    
    def add(capture) → None
        # Lock + dict[id] = capture
        # Appelle _maybe_snapshot()
    
    def list() → List
        # Lock + return list(_store.values())
    
    def geojson() → Dict
        # Exporte chaque capture en Feature GeoJSON
        # geometry: Point [lon, lat]
        # properties: capture_id, kind, state, trust_score, flags
```

**Choix en-mémoire :**
- **Rapidité** : pas d'I/O disque
- **Snapshot JSON** : point d'inspection `backend/data/captures_snapshot.json`
- **Production** : serait remplacé par PostGIS/PostgreSQL

**Thread-safety :**
- `threading.Lock` protège `_store` en lecture/écriture
- Snapshot écrit en section critique (avoid race conditions)

#### EventBus (In-Process)
```python
class EventBus:
    _events: List[DomainEvent]
    
    def emit(event: DomainEvent) → None
        # Ajoute à queue + log
    
    def recent(n: int) → List[DomainEvent]
        # Retourne N derniers événements
    
    @property
    def event_count() → int
```

Bus événementiel simple ; enregistre tous les DomainEvents. Sert endpoint `/api/events` pour monitoring. Peut être étendu pour publier vers Kafka/RabbitMQ en prod.

#### PluginSystem (Extensibilité)
```python
class PluginSystem:
    _plugins: Dict[str, Dict]  # capteurs découverts
    
    def register(name, config) → None
    
    def snapshot() → List[Dict]
```

Registry des capteurs/plugins disponibles. Endpoint `/api/plugins` expose la liste. Futur : permet d'ajouter nouveaux types de capture (température, humidité, etc.) dynamiquement.

## Flux complet de capture

### 1. Agent mobile crée capture
```
Appui FAB (pothole)
  ↓
GpsService.current() → Position {lat, lon, accuracy}
  ↓
POST /api/captures {lat, lon, kind, signals}
```

### 2. Serveur reçoit
```
Handler.do_POST()
  ↓
Content-Length + JSON parse
  ↓
service.create_capture(lat=..., lon=..., kind=...)
  ↓
Crée Capture(id=UUID, point=GeoPoint, state=NEW)
  ↓
repo.add(capture)
  ↓
bus.emit(gps_captured event)
  ↓
Retourne capture.to_dict() + 201
```

### 3. Agent obtient confirmation
```
Reçoit {"capture_id": "cap_123", "state": "new", ...}
  ↓
Marque localement SYNCED
  ↓
Base SQLite sauvegardée
```

### 4. Agent peut requérir progression
```
POST /api/captures/cap_123/sync {via_mesh: false}
  ↓
service.sync_capture(cap_123)
  ↓
StateMachine: NEW → ACKNOWLEDGED
  ↓
Retourne {"state": "acknowledged", ...}
```

### 5. Frontend Leaflet affiche
```
GET /api/captures.geojson
  ↓
repo.geojson() exporte Features
  ↓
Leaflet L.geoJson(data).addTo(map)
  ↓
Marqueurs colorés par trust_score
```

## Architecture frontend (statique)

### index.html (Leaflet)
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9/dist/leaflet.css" />
<script src="...leaflet.js"></script>

<div id="map"></div>

<script>
  const map = L.map('map').setView([12.37, -1.52], 14);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
  
  // Fetch captures GeoJSON
  fetch('/api/captures.geojson')
    .then(r => r.json())
    .then(data => {
      L.geoJson(data, {
        pointToLayer: (feature, latlng) => {
          const trust = feature.properties.trust_score;
          const color = trust >= 0.6 ? 'green' : trust >= 0.3 ? 'orange' : 'red';
          return L.circleMarker(latlng, { color, radius: 8 });
        }
      }).addTo(map);
    });
</script>
```

Leaflet = port open-source de Mapbox GL; utilise tuiles raster OSM (OpenStreetMap). Léger, sans dépendance.

## Configuration & Démarrage

### Env vars
```bash
MAPNET_HOST=0.0.0.0         # Écoute all interfaces
MAPNET_PORT=8080            # Port HTTP
MAPNET_SEED_N=30            # Nombre captures démo au boot
```

### Démarrage
```bash
python backend/presentation/server.py
# [MapNet] DDD backend + Leaflet map serving on http://0.0.0.0:8080
# [MapNet] seeded 30 captures, 0 domain events
```

Puis naviguer vers `http://localhost:8080` pour la carte.

### Docker
```yaml
# docker-compose.yml
services:
  mapnet:
    build: .
    ports:
      - "8080:8080"
    environment:
      MAPNET_SEED_N: 50
```

## Justifications des choix architecturaux

### DDD (Domain-Driven Design)
- **Séparation nette** : présentation (HTTP) / application (services) / domaine (logique pur) / infrastructure (persistance)
- **Testabilité** : domaine indépendant de HTTP, DB, etc. (pure Python functions + classes)
- **Maintenabilité** : boundaries claires ; facile de changer impl persistance (in-mem → PostgreSQL)
- **Collaboration métier** : Capture/CaptureState/QualityReport sont concepts explicites, pas des `dicts` magiques

### Stdlib http.server (zéro dépendance)
- **Reproductibilité** : pas de pip install si entraînement ADAN fragile
- **Légèreté** : démarrage < 100ms
- **Limitation** : pas de ORM, middleware, routing avancé (mais pas besoin ici)
- **Production** : Uvicorn/Gunicorn wraps stdlib si scaling nécessaire

### In-memory + snapshot JSON
- **Développement rapide** : pas setup PostgreSQL
- **Inspection** : `cat backend/data/captures_snapshot.json` pour voir l'état
- **Persistance** : snapshot écrit à chaque modification via repo
- **Prod** : remplaceable ; interface `CaptureRepository` abstraite

### Event sourcing (DomainEvents)
- **Audit complet** : chaque capture a un historique d'événements
- **Debugging** : `/api/events` expose 30 derniers pour monitoring
- **Extensibilité** : futur : rejouer, réagir en temps réel, intégrations webhooks

### ThreadingHTTPServer
- **Multi-request** : ThreadingHTTPServer accepte requêtes simultanées (pas single-threaded)
- **Concurrent captures** : N agents peuvent POST en parallèle
- **Lock coordination** : InMemoryRepository protège `_store` via `threading.Lock`

### GeoJSON export
- **Standard geospatial** : RFC 7946
- **Leaflet natif** : `L.geoJson(data)` parse directement
- **Interopérabilité** : peut importer dans QGIS, ArcGIS, etc.

### CORS wildcard
- **Développement** : frontend Dart/JS cross-origin sans blocage navigateur
- **Prod** : restreindre à domaines sécurisés (`Access-Control-Allow-Origin: https://myapp.com`)

## Limitations & améliorations futures

### Actuelles
- Persistance en-mémoire seul (perte si crash)
- Authentification absente (API publique)
- Pas de pagination (liste complète à chaque GET)
- Stockage captures limité par RAM

### Potentielles
- **PostgreSQL/PostGIS** : persistance durable + queries spatiales (ST_Distance)
- **Authentication** : Bearer tokens, OAuth2
- **Pagination** : limit/offset sur /api/captures
- **Événements temps réel** : WebSocket pour push vers frontend
- **Caching** : Redis pour GeoJSON pré-rendu
- **Clustering spatial** : Markercluster Leaflet pour zoom < 10
- **Indexation** : rtree spatial pour queries rapides par zone
- **Export** : CSV/Shapefile pour arcGIS
