# MapNet — Cartographie collaborative offline-first pour le terrain

**Version :** 2.1 mobile

**Statut :** Opérationnel — backend, carte Leaflet et deux applications Android

**Dernière validation :** 31 août 2026

---

## 📌 À propos

**MapNet** est une application mobile Android + serveur backend pour la **cartographie collaborative en temps réel** sur le terrain. Elle combine :

- 📱 **Mobile offline-first** (Flutter/Dart) : capture GPS précise + IMU réel
- 🗺️ **Backend DDD** (Python) : state machine + event sourcing
- 🌐 **Synchronisation bidirectionnelle** (DTN-compatible) : PUSH/PULL automatique
- 🧭 **Capteurs terrain réels** : boussole, accéléromètre, gyroscope, pédomètre
- 📍 **Indexation quartiers** : reverse-geocoding Nominatim + administratif

**Cas d'usage :** Agents terrain à Yaoundé cartographient routes/POI → données synchronisées VPS → coordinateurs voient agents + captures en temps réel.

---

## État opérationnel

| Capacité | État livré |
|----------|------------|
| MapNet Terrain Android | Capture GPS/capteurs, navigation, stockage local et synchronisation vers le backend DDD |
| MapNet Data Mule Android | Dashboard hors-ligne et synchronisation différentielle manifest/delta via la Gateway Go |
| Synchronisation offline-first | Retry exponentiel persistant, 5 essais, dead-letter, historique et idempotence `capture_id` |
| Agents | `Device`/`DeviceSession`, heartbeat 30 s, online/offline et GeoJSON combiné |
| Quartiers | Reverse-geocoding Nominatim, cache disque et filtre Leaflet dynamique |
| Capteurs | Boussole, accéléromètre, gyroscope et pédomètre physiques ; données absentes affichées comme indisponibles |
| Centre géographique | Yaoundé (`3.8480, 11.5021`) sur backend, carte et mobile |
| Données synthétiques runtime | Aucune : les chemins de seed mobile et backend ont été supprimés |

Les scores de qualité sont renormalisés uniquement sur les mesures physiques réellement disponibles. `None` signifie « indisponible » ; aucune constante de capteur n'est substituée.

---

## 📚 Documentation

### Pour commencer rapidement

**→ [`docs/INDEX.md`](docs/INDEX.md)** — Point d'entrée unique  
Navigation guidée, chemins de lecture par rôle (décideurs, tech leads, devs)

**→ [`docs/executive-summary.md`](docs/executive-summary.md)** — Vision 15 min  
KPIs, problèmes critiques, stratégie MVP, budget & risques

### Audit technique (V2)

**→ [`docs/diagnostic-problemes.md`](docs/diagnostic-problemes.md)** — Analyse 20 min  
6 problèmes identifiés + code snapshots + causes racines  
✓ Taux sync réel calculé : 25%  
✓ Captures snapshot analysées  
✓ Mesures proposées

**→ [`docs/mvp-feuille-route.md`](docs/mvp-feuille-route.md)** — Plan détaillé 60 min  
4 phases MVP (8 semaines), code + dépendances  
✓ Phase 1 : Retry exponentiel (Sync 25% → 75%+)  
✓ Phase 2 : Device tracking (Agents 0% → 100%)  
✓ Phase 3 : Quartiers (reverse-geocoding)  
✓ Phase 4 : Capteurs réels (compass, IMU, pedometer)  
✓ Checklist acceptation par phase  
✓ Budget & ressources (120h, 60 USD)

### Architecture (référence)

**→ [`docs/application-mobile.md`](docs/application-mobile.md)** — Mobile (Flutter)  
Services (GPS, Sync, Persistence), modèles, flux utilisateur  
Stack : Flutter 3.24, Dart 3.5, SQLite, http/geolocator

**→ [`docs/carte-serveur.md`](docs/carte-serveur.md)** — Backend (Python)  
DDD (Présentation/App/Domaine/Infra), 9 endpoints REST  
State machine 7 états, quality pipeline, event bus

---

## 🚀 Démarrage rapide

**→ [`docs/QUICK-START.md`](docs/QUICK-START.md)** — Instructions complètes (clonage + setup)  
3 façons de récupérer : Git, ZIP, GitHub Desktop  
Troubleshooting complet + checklist

### Pré-requis

**Mobile :**
```bash
flutter --version  # 3.24.5+
dart --version     # 3.5.4+
```

**Backend :**
```bash
python --version   # 3.10+
# Zéro dépendance pip (stdlib uniquement)
```

### Installation locale

#### 1. Cloner le repo

```bash
git clone https://github.com/Cabrel10/Mapnet.git
cd Mapnet
git checkout genspark_ai_developer  # Branche avec V2 audit
```

#### 2. Mobile (Flutter)

```bash
cd mobile

# Installer dépendances
flutter pub get

# Lancer sur émulateur/device
flutter run

# Ou build APK
flutter build apk --release
```

**Config :** `mobile/lib/config/app_config.dart`
- `serverUrl` : gateway déployée (défaut : `http://169.58.67.16:8088`)
- `syncIntervalSeconds` : Cadence sync (défaut : 20s)

#### 3. Data Mule (Flutter)

```bash
cd services/mobile-client
flutter pub get
flutter test
flutter build apk --release \
  --dart-define=MAPNET_GATEWAY=http://169.58.67.16:8080
```

Les deux APK universels installables sont publiés dans `apk_dist/` :

- `mapnet-terrain-v1.1.0.apk` (`com.cabrel10.mapnet_mobile`) ;
- `mapnet-data-mule-v1.1.0.apk` (`com.cabrel10.mapnet_mobile_client`).

#### 4. Backend (Python)

```bash
cd backend

# Démarrer serveur HTTP
python presentation/server.py

# Env vars optionnels
export MAPNET_HOST=0.0.0.0
export MAPNET_PORT=8088

python presentation/server.py
```

Accès local : `http://localhost:8088` — aucune capture de démonstration n'est générée.

#### 5. Docker (optionnel)

```bash
docker-compose up -d

# Logs
docker-compose logs -f mapnet
```

---

## 📂 Structure du projet

```
Mapnet/
├── docs/                          # Documentation (audit V2 + architecture)
│   ├── INDEX.md                   # Point d'entrée navigation
│   ├── executive-summary.md        # Vision décideurs (15 min)
│   ├── diagnostic-problemes.md     # Audit technique (20 min)
│   ├── mvp-feuille-route.md        # Plan MVP détaillé (60 min)
│   ├── application-mobile.md       # Architecture mobile
│   ├── carte-serveur.md            # Architecture backend
│   └── lettre-ccaa.md              # Contexte projet
│
├── mobile/                        # App Flutter (Android)
│   ├── lib/
│   │   ├── main.dart              # Entry point
│   │   ├── config/
│   │   │   └── app_config.dart    # Config réseau
│   │   ├── services/
│   │   │   ├── gps_service.dart   # GPS temps réel ✓
│   │   │   ├── sync_service.dart  # Sync bidirectionnelle (à améliorer P1)
│   │   │   └── geo_utils.dart     # Utils haversine
│   │   ├── database/
│   │   │   └── local_store.dart   # SQLite persistence
│   │   ├── models/
│   │   │   └── capture.dart       # Modèle capture
│   │   └── screens/
│   └── pubspec.yaml               # Dépendances
│
├── backend/                       # Backend Python DDD
│   ├── presentation/
│   │   ├── server.py              # HTTP handler (stdlib)
│   │   ├── container.py           # Composition root
│   │   └── static/
│   │       └── index.html         # Carte Leaflet
│   ├── application/
│   │   ├── capture_service.py     # Use cases
│   │   ├── event_bus.py           # Event bus
│   │   └── plugins.py             # Plugin system
│   ├── domain/
│   │   ├── entities.py            # Capture, GeoPoint aggregates
│   │   ├── events.py              # Domain events
│   │   ├── quality.py             # Quality pipeline
│   │   ├── state_machine.py       # State machine captures
│   │   └── schema.py              # Schema versioning
│   ├── infrastructure/
│   │   └── memory_repo.py         # In-memory repository
│   └── data/
│       └── captures_snapshot.json  # Snapshot persistance
│
├── docker-compose.yml             # Docker config
├── .gitignore
├── LICENSE
└── README.md                      # Ce fichier
```

---

## 🔄 Plan MVP (8 semaines)

### Phase 1 : Taux sync > 75% (Semaines 1-2)
**Coût :** 4 jours dev

Changements :
- `app_config.dart` : backoff config (1s, 2s, 4s, 8s, 16s)
- `sync_service.dart` : retry loop + `NetworkService.isConnected()`
- `local_store.dart` : table `sync_retries`
- `server.py` : idempotence (capture_id check)

**Résultat :** Captures ne se perdent jamais, même 30s offline

### Phase 2 : Agent visibility 100% (Semaines 2-3)
**Coût :** 5 jours dev

Changements :
- Backend : `Device` + `DeviceSession` aggregates
- Mobile : heartbeat timer (30s) + location broadcast
- Backend : `/api/devices/heartbeat` + `/api/map.geojson`
- Frontend : agents bleus (connectés) vs gris (60s timeout)

**Résultat :** Coordinateurs voient agents temps réel sur carte

### Phase 3 : Quartiers indexation (Semaines 3-4)
**Coût :** 4 jours dev

Changements :
- Backend : `NominatimCache` (reverse-geocoding + 24h TTL)
- Mobile : `LocationService.getNeighborhoodName()`
- Frontend : filter dropdown (Médina, Kouara, etc.)

**Résultat :** Toutes captures taggées quartier administratif

### Phase 4 : Capteurs réels (Semaines 4-8)
**Coût :** 10 jours dev

Changements :
- Compass : `flutter_compass` + heading HUD
- IMU : `sensors_plus` + spoofing detection
- Pedometer : `pedometer` + daily counter
- UI : sync log detail sheet + retry history

**Résultat :** Données réelles (pas mock), trust scores multi-sensor

**Total :** 120 heures dev, 60 USD infra → Prêt production 100 agents

---

## Garanties de données terrain

- Le mobile lit exclusivement les API natives exposées par `geolocator`, `flutter_compass`, `sensors_plus` et `pedometer`.
- Le HUD masque les métriques indisponibles au lieu d'inventer une valeur.
- Le backend marque la provenance `physical_capture_signals_only` et publie `metrics_are_physical: true`.
- Les captures sont idempotentes par identifiant client, y compris après une perte de réponse HTTP.
- La carte sépare explicitement les features `capture` et `device`, avec expiration online/offline.

---

## 📖 Guide par rôle

### Je suis décideur/PM
1. Lire [`docs/executive-summary.md`](docs/executive-summary.md) (15 min)
2. Lire section "Plan MVP" ci-dessus (10 min)
3. Valider budget & timeline (voir Phase 1-4)

### Je suis tech lead/architect
1. Lire [`docs/diagnostic-problemes.md`](docs/diagnostic-problemes.md) (20 min)
2. Lire [`docs/mvp-feuille-route.md`](docs/mvp-feuille-route.md) (60 min)
3. Assigner phases à équipe dev

### Je suis développeur mobile
1. Lire [`docs/application-mobile.md`](docs/application-mobile.md) (30 min)
2. Lire [`docs/mvp-feuille-route.md`](docs/mvp-feuille-route.md) Phase 1-4 sections mobile
3. Commencer Phase 1 (`app_config.dart` + `sync_service.dart`)

### Je suis développeur backend
1. Lire [`docs/carte-serveur.md`](docs/carte-serveur.md) (35 min)
2. Lire [`docs/mvp-feuille-route.md`](docs/mvp-feuille-route.md) Phase 1-4 sections backend
3. Commencer Phase 1 (`server.py` idempotence)

---

## 🔗 Récupérer cette version

**→ Voir [`docs/QUICK-START.md`](docs/QUICK-START.md) pour guide complet (recommandé)**

### Option 1 : Git (rapide)

```bash
git clone https://github.com/Cabrel10/Mapnet.git
cd Mapnet
git checkout genspark_ai_developer
```

### Option 2 : ZIP (snapshot)

```bash
curl -L https://github.com/Cabrel10/Mapnet/archive/genspark_ai_developer.zip -o Mapnet.zip
unzip Mapnet.zip
cd Mapnet-genspark_ai_developer
```

### Option 3 : Docker

```bash
docker build -t mapnet:v2 .
docker run -p 8080:8080 mapnet:v2
```

**Troubleshooting :** Voir [`docs/QUICK-START.md`](docs/QUICK-START.md) section "Troubleshooting"

---

## 📋 Checklist déploiement MVP

### Phase 1 (Taux sync)
- [ ] `app_config.dart` : backoff config
- [ ] `sync_service.dart` : retry loop
- [ ] `local_store.dart` : sync_retries table
- [ ] `server.py` : idempotence check
- [ ] Test : 10 captures, offline 45s, tous synced après
- [ ] KPI : sync > 75%

### Phase 2 (Agent visibility)
- [ ] Device + DeviceSession domain
- [ ] Mobile : heartbeat + location broadcast
- [ ] Backend : `/api/devices/heartbeat` + `/api/map.geojson`
- [ ] Frontend : agents bleus
- [ ] Test : 2 agents simultanés, déconnexion → gris
- [ ] KPI : visibility 100%

### Phase 3 (Quartiers)
- [ ] `NominatimCache` backend
- [ ] Mobile : `LocationService`
- [ ] Frontend : filter dropdown
- [ ] Test : 5 captures Ouaga → tous quartier identifié
- [ ] KPI : quartiers 75%+

### Phase 4 (Capteurs)
- [ ] Compass : `flutter_compass` + HUD
- [ ] IMU : `sensors_plus` + spoofing
- [ ] Pedometer : `pedometer` + counter
- [ ] UI : sync log detail
- [ ] Test : IMU spoofing detect
- [ ] KPI : capteurs 100%, UI transparent

---

## 🧪 Tests

### Mobile (Flutter)
```bash
cd mobile
flutter test                  # Dart tests
flutter analyze               # Linting
flutter build apk --debug     # Build debug APK
```

### Backend (Python)
```bash
cd backend
python -m pytest tests/       # Tests (si existants)
python presentation/server.py # Run server

# Test endpoint
curl http://localhost:8080/api/captures.geojson
```

---

## 📊 Fichiers clés à modifier (MVP)

### Mobile
- `mobile/lib/config/app_config.dart` → Backoff config (Phase 1)
- `mobile/lib/services/sync_service.dart` → Retry loop (Phase 1)
- `mobile/lib/database/local_store.dart` → sync_retries table (Phase 1)
- `mobile/lib/main.dart` → Capteurs + UI (Phase 4)
- `mobile/pubspec.yaml` → Dépendances (Phase 2, 3, 4)

### Backend
- `backend/presentation/server.py` → Idempotence (Phase 1), Devices (Phase 2)
- `backend/domain/entities.py` → Device aggregate (Phase 2)
- `backend/infrastructure/memory_repo.py` → DeviceSessionRepository (Phase 2)
- `backend/domain/geography.py` → NominatimCache (Phase 3, créer)

---

## 🤝 Contribution

**Branches :**
- `main` : production (stabilité)
- `genspark_ai_developer` : développement V2 (audit + MVP)
- `feature/*` : nouvelles fonctionnalités

**PR :**
1. Fork → feature branch → PR
2. CI checks (lint, tests)
3. Code review
4. Merge to `genspark_ai_developer` (staging), puis `main`

---

## 📜 Licence

MapNet est distribué sous licence MIT — Voir [`LICENSE`](LICENSE)

---

## 📞 Support

**Questions ?**
- 📖 Voir [`docs/INDEX.md`](docs/INDEX.md) pour navigation
- 🔍 Problèmes : [`docs/diagnostic-problemes.md`](docs/diagnostic-problemes.md)
- 🛠️ MVP : [`docs/mvp-feuille-route.md`](docs/mvp-feuille-route.md)

**Status actuel :** 🟠 Audit V2 terminé (30 juillet 2026)  
**MVP start :** 1er août 2026  
**MVP fin :** 26 septembre 2026

---

**Généré automatiquement par audit MapNet V2 — 30 juillet 2026**
