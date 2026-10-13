# Architecture MapNet Mobile

## Vue d'ensemble

**MapNet Mobile** est une application Android de cartographie hors-ligne conçue pour la capture géoréférencée collaborative sur le terrain. Elle suit une architecture **Offline-First / DTN (Delay-Tolerant Network)**, permettant aux agents de travail (releveurs terrain) de collecter des données GPS précises avec synchronisation bidirectionnelle vers un serveur VPS centralisé.

## Stack technologique

### Framework & Runtime
- **Flutter 3.24.5** — Framework cross-platform (actuellement Android API 29-34)
- **Dart 3.5.4** — Langage compilé vers machine native (Arm64)

### Dépendances principales

#### Cartographie & Géolocalisation
| Package | Version | Raison |
|---------|---------|--------|
| `flutter_map` | 7.0.2 | Rendu de tuiles raster (Leaflet-like) ; supporte MBTiles hors-ligne pour cartes pré-téléchargées |
| `latlong2` | 0.9.1 | Types géographiques (LatLng) ; calculs haversine pour distance/cap |
| `geolocator` | 12.0.0 | GPS haute précision avec HDOP/VDOP ; compatibilité Flutter 3.24 (geolocator_android 4.x) |

**Justification geolocator v12** : Version 14+ tire `geolocator_android 5.0.3` qui appelle `Color.toARGB32()` (API Flutter 3.27+). Casse `compileFlutterBuildRelease` sur Flutter 3.24. Version 12 reste compatible avec la dernière ligne stabilisée d'Android geolocator.

#### Persistance locale (SQLite)
| Package | Version | Raison |
|---------|---------|--------|
| `sqflite` | 2.3.3+1 | Base SQLite transactionnelle embarquée ; stoking des captures hors-ligne (sync_dataset, telemetry, road_attr) |
| `path_provider` | 2.1.4 | Localise le dossier `/data/data/.../documents/` pour la DB portable |
| `path` | 1.9.0 | Construction de chemins cross-platform |

#### Réseau & Synchronisation
| Package | Version | Raison |
|---------|---------|--------|
| `http` | 1.2.2 | Client HTTP HTTP/1.1 ; sync différée vers VPS (PUSH/PULL captures) |

#### Permissions runtime
| Package | Version | Raison |
|---------|---------|--------|
| `permission_handler` | 11.3.0 | Dialogue interactif d'autorisation (Location/Storage) au lancement Android 10+ |

## Architecture interne

### 1. Couche présentation (UI)

#### Écran principal : `FieldMapScreen`
```
FieldMapScreen (_FieldMapScreenState)
├── MapController
│   └── Flutter Map (Leaflet layer + markers + halo d'incertitude)
├── LocalStore (singleton)
│   └── SQLite DB (captures table)
├── GpsService (singleton)
│   └── Geolocator stream + position actuelle
├── SyncService (singleton)
│   └── Timer périodique (PUSH/PULL)
└── UI Overlays
    ├── HUD (GPS ±m, HDOP, réseau, pts, attente synchro)
    ├── Badge synchro (nuage + état)
    ├── FABs captures (pothole / note vocale / POI)
    └── Bouton "proximité" + recentrage
```

**Flux de la caméra :**
- Mode `_followMe=true` (défaut) : la caméra centre l'utilisateur en temps réel (flutter_map MovedCamera)
- Geste utilisateur → `_followMe=false` (pause suivi)
- Bouton recentrage → réactive le suivi

**Halo d'incertitude :**
- `CircleMarker` autour de `_myPos` avec rayon = `_accuracyM` (précision réelle du GPS en mètres)
- Couleur semi-transparente bleu (RGB 33,150,243 @ 15% opacité) avec bordure plus visible
- Se met à jour chaque nouvelle position du stream GPS

**Marqueurs de capture :**
- Icône colorée par `trustScore` : 
  - `trust >= 0.6` → vert (#00E5A0)
  - `0.3 <= trust < 0.6` → orange (#F57C00)
  - `trust < 0.3` → rouge (#EF4444)
- Taille différente si c'est un point à soi (owner=1) ou autre agent (owner=0)

#### Dialogue permissions (onboarding)
Au lancement, `_bootstrap()` appelle `GpsService.ensurePermissions()` :
1. Vérifie que le service de localisation OS est activé
2. Demande permission interactif `ACCESS_FINE_LOCATION` (modal système Android)
3. Demande permission stockage (non-bloquant)
4. Retourne l'état (granted / denied / deniedForever / serviceDisabled)

Si refusée, affiche un `ModalBottomSheet` avec explication et bouton "OUVRIR LES RÉGLAGES" (ouvre `openAppSettings()`)

#### Dialogue proximité
Bouton Explore → `_showNearby()` → calcule distance haversine vers chaque capture :
- Trie par proximité ascendante
- Affiche azimut (cap) et rose des vents 8 directions (N, NE, E, SE, S, SO, O, NO)
- Tap → navigue vers la capture (map zoom 17)
- Pause le suivi utilisateur (`_followMe=false`)

### 2. Couche services

#### `GpsService` (singleton)
```dart
GpsService
├── ensurePermissions() → GpsPermissionResult
├── openSettings() → Dart:platform
├── current() → Future<Position>  // Fix ponctuel haute précision (15s timeout)
├── stream() → Stream<Position>   // Flux continu (distanceFilter: 5m)
└── hdopFromAccuracy(m) → double  // Proxy HDOP depuis précision
```

**Précision GPS réelle :**
- Chaque `Position` inclut un champ `.accuracy` (mètres)
- Pas codé en dur ; provient du capteur matériel (Android `LocationManager.onLocationChanged()`)
- Permet un HUD dynamique montrant ±X m réels

**HDOP proxy :**
- Plugin geolocator ne remonte pas HDOP brut ; on dérive depuis accuracy
- Convention : 5 m d'incertitude ≈ HDOP 1.0
- Formule : `HDOP = (accuracy / 5).clamp(0.5, 50)`

#### `LocalStore` (singleton)
```dart
LocalStore
├── init() → Future (ouvre/crée mapnet_terrain.db)
├── insertCapture(Capture) → Future (UPSERT)
├── loadCaptures() → Future<List<Capture>>
├── unsynced() → Future<List<Capture>>  // sync_state != 'SYNCED'
├── markSynced(id) → Future
├── markState(id, state) → Future
├── recordRetry(...) → Future  // ETA, erreur et dead-letter
├── syncHistory() → Future<List<Map>>
└── upsertRemote(Capture) → Future  // download serveur (owner=0)
```

**Schéma SQLite v2 :**
```sql
CREATE TABLE captures (
  id TEXT PRIMARY KEY,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  type TEXT NOT NULL,
  trust_score REAL NOT NULL,
  sync_state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  accuracy_m REAL NOT NULL DEFAULT 0,       -- ajout v2
  owner INTEGER NOT NULL DEFAULT 1          -- ajout v2
)

CREATE TABLE local_telemetry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL
)
```

**Statuts synchro :**
- `PENDING` — capture locale créée, pas encore envoyée
- `SYNCED` — confirmée côté serveur
- `FAILED_RETRY` — tentative échouée, réessayera

**Owner field :**
- `1` — capture à moi (téléphone actuel)
- `0` — capture téléchargée d'autre agent

#### `SyncService` (singleton)
```dart
SyncService
├── start(onResult) → void  // Timer périodique + callback UI
├── stop() → void
└── syncOnce() → Future<SyncOutcome>
    ├── _pushOne(Capture) → Future<bool>
    └── _pullAll() → Future<int>
```

**Cycle complet PUSH + PULL :**
1. PUSH : récupère captures `PENDING` où `owner=1`
   - POST chacune vers `/api/captures` (Body : lat/lon/kind/signals)
   - Si 201/200 → `markSynced()` ; sinon → `FAILED_RETRY`
2. PULL : GET `/api/captures`
   - Sérialise chaque item en `Capture.fromServer()` (owner=0)
   - Avoid loop : skip IDs déjà présents localement avec `owner=1`
   - `upsertRemote()` → stocke/fusionne

**Intervalle & Timeout :**
- Défaut : `AppConfig.syncIntervalSeconds` (probablement 30-60s)
- Timeout HTTP : `AppConfig.httpTimeout` (probablement 15s)
- Boucle jamais jette d'exception ; renvoie `SyncOutcome(online=false, error=...)`

#### `GeoUtils`
```dart
GeoUtils
├── distanceMeters(LatLng, LatLng) → double  // haversine
├── bearingDeg(LatLng, LatLng) → double      // azimut 0-360
├── compass(bearing) → String                // rose 8 directions
└── humanDistance(m) → String                // formatage "123 m" / "1.2 km"
```

### 3. Couche données

#### `Capture` (modèle)
```dart
class Capture {
  String id;
  double lat, lon;
  CaptureType type;  // enum: roadDamage, voiceNote, poi
  double trustScore;
  String syncState;  // PENDING, SYNCED, FAILED_RETRY
  DateTime createdAt;
  double accuracyM;  // précision GPS réelle (m)
  int owner;         // 1=moi, 0=autre agent
  
  toMap() → Map<String, dynamic>  // pour SQLite
  fromMap() → static
  fromServer() → static  // serveur JSON → Capture(owner=0)
  serverKind → String    // type Dart → kind serveur ("gps", "road_condition", "poi_created")
}

enum CaptureType {
  roadDamage(Icons.warning_amber, "Dégât routier"),
  voiceNote(Icons.mic, "Note vocale"),
  poi(Icons.add_location_alt, "Point d'intérêt"),
}
```

#### `AppConfig`
```dart
class AppConfig {
  static const String baseUrl = "http://...";  // VPS IP:port
  static const String capturesEndpoint = "$baseUrl/api/captures";
  static const int syncIntervalSeconds = 30;
  static const Duration httpTimeout = Duration(seconds: 15);
}
```

## Flux utilisateur complet

### 1. Démarrage + permission
1. `main()` → `FieldMapScreen`
2. `initState()` → `_bootstrap()`
3. `GpsService.ensurePermissions()`
   - Si non accordée → affiche modal + propose paramètres
   - Si accordée → continue
4. `LocalStore.init()` + charge captures précédentes
5. `_startGps()` → lance stream continu + fix initial
6. `_startSync()` → lance timer PUSH/PULL

### 2. Capture à la position réelle
1. Appui FAB (pothole / note / POI)
2. `_capture(CaptureType)` vérifie `_permGranted && _myPos != null`
3. `GpsService.current()` → demande fix haute précision (15s)
4. Calcule `trust = (1 - (accuracy/50)).clamp(0.2, 0.98)` depuis accuracy GPS réelle
5. Crée `Capture(syncState='PENDING', owner=1)`
6. `LocalStore.insertCapture()` → SQLite
7. `SyncService.syncOnce()` immédiat (essai PUSH)
8. Toast confirmation "±X.X m — file de synchro"

### 3. Synchronisation sans réseau (DTN)
- App capture et stock localement même sans connexion
- Timer lance `syncOnce()` périodiquement
- Dès que réseau revient → PUSH automatique vers VPS
- PULL simultanée → télécharge points d'autres agents

### 4. Navigation proximité
1. Bouton Explore
2. `_showNearby()` calcule distance haversine depuis `_myPos` vers chaque capture
3. Affiche liste triée + azimut (N, NE, E, SE, S, SO, O, NO)
4. Tap un élément → zoom caméra vers ce point (lat/lon)
5. Pause suivi utilisateur (`_followMe=false`)
6. Bouton recentrage → réactive

## Justifications des choix techniques

### Flutter + Dart
- Cross-platform (Android + potentiel iOS)
- Native performance sur ARM64
- Hot reload pour itération rapide

### flutter_map v7 (Leaflet port)
- Tuiles raster standard (OSM)
- Support futur MBTiles hors-ligne
- Écosystème plugin mature

### geolocator v12
- Seule version stable compatible Flutter 3.24 sans breaking changes API
- HDOP/VDOP ne sont pas exposés directement (limitation android native) → dérivé depuis accuracy

### SQLite sqflite v2.3
- **Offline-First** : captures stockées même sans VPS
- **Transactionnel** : writes threadsafe (mutex interne)
- **Snapshot JSON** possible → inspection/debug
- **Schéma versionné** : onUpgrade pour migrations (v1→v2 a ajouté accuracy_m, owner)

### Sync bidirectionnelle (PUSH/PULL)
- PUSH : envoie captures locales `owner=1` vers VPS
- PULL : télécharge **tout** depuis VPS, marque `owner=0` pour éviter loops
- Permet collaboration multi-agents sur même terrain
- DTN-compatible : reconnecte automatiquement dès que réseau revient

### Halo d'incertitude
- Cercle transparent autour de `_myPos` avec rayon = accuracy GPS réelle
- Montre l'utilisateur où il se trouve **précisément** (pas approximatif)
- Radius in meters, pas pixels : indépendant du zoom

### HUD temps réel (GPS, HDOP, réseau, points, attente)
- Affiche état réseau en direct (EN LIGNE / HORS-LIGNE)
- Affiche nombre captures + captures en attente synchro
- Affiche précision GPS réelle (±X m) + proxy HDOP
- Mise à jour chaque tick du stream GPS

## Limitations & améliorations futures

### Actuelles
- GPS uniquement (pas IMU, pas baromètre)
- MBTiles pré-téléchargés non encore intégrés
- Authentification serveur absente (pas de token Bearer)
- Import/export captures limité

### Potentielles
- Support iOS (dart:io platform channels)
- Stockage chiffré SQLite (sqflite_common_ffi + sqlcipher)
- Cache tuiles raster pour mode hors-ligne complet
- Peer-to-peer via Bluetooth/NFC (mesh DTN)
- Historique captures avec versioning
