# MapNet V2 — Executive Summary

**Date :** 30 juillet 2026  
**Auteur :** Audit technique MapNet  
**Audience :** Équipe produit, stakeholders

---

## Situation actuelle

Le projet **MapNet** (cartographie collaborative terrain, offline-first, DTN) a atteint une **architecture DDD solide** avec stack Flutter mobile + Python backend. **Cependant**, le système n'atteint **aucun des KPIs critiques** définis :

| KPI | Cible | Actuel | Écart |
|-----|-------|--------|-------|
| Taux sync mobile ↔ serveur | > 75% | 25% | -66% |
| Agents visibles sur carte | 100% | 0% | -100% |
| Indexation quartiers | 75% | 0% | -100% |
| Capteurs réels | 100% | 0% | -100% |
| État sync transparent | 100% | 50% | -50% |

---

## Problèmes identifiés

### 1. Taux synchronisation 25% (Objectif > 75%)

**Racine :** Pas de retry exponentiel + timeout HTTP insuffisant (10s sur 3G).

```
État snapshot serveur :
├─ SERVER_CONFIRMED : 11 captures (25%)  ← Sync réussi
├─ ENCRYPTED : 33 captures (75%)         ← Jamais envoyées
```

**Impact :**
- 33 captures sur 44 = perdues après 48h offline
- Agents frustration : "Mon travail terrain disparaît"
- Données manquantes : reports terrain incomplets

### 2. Agents invisibles sur carte (0% vs 100%)

**Racine :** Pas de `device_id` dans architecture. Carte affiche captures, pas agents.

```
Cas d'usage manquant :
  John (téléphone) capture à 12.37°N → John doit apparaître BLEU sur carte
  John déconnecte 15 min → John disparaît (gris)
  
État réel :
  Seuls POI/routes visibles, agents = INVISIBLES
```

**Impact :**
- Coordonnateurs terrain ne voient pas où sont les agents
- Alertes temps réel impossibles
- Pas de tracé de mission

### 3. Quartiers inexistants (0% vs 75%)

**Racine :** Pas de PostGIS, pas de reverse-geocoding (Nominatim).

```
Agents ne savent pas :
  - Quel quartier ils cartographient
  - Quels rapports sont "prioritaires" par zone
  - Où poster les captures géographiquement
```

**Impact :**
- Navigation terrain : "go to nearby captures" = distance seule, pas nom quartier
- Reporting : captures non localisées administrativement
- Gestion : impossible de filtrer par arrondissement

### 4. Capteurs 100% mock

**Boussole :** Dérivée math from GPS accuracy, pas magnétomètre réel  
**Gyro/Accél :** Mock constants, jamais IMU vrai  
**Pédomètre :** N'existe pas  

**Impact :**
- Trust scores artificiels (basés GPS seul, pas mouvement)
- Détection spoofing GPS impossible
- Données "mouvement terrain" absentes

---

## Stratégie de résolution

**MVP en 8 semaines** (4 phases parallèles) :

| Phase | Semaines | Focus | KPI Cible |
|-------|----------|-------|-----------|
| 1 | 1-2 | Retry exponential + network detection | Sync 75%+ |
| 2 | 2-3 | Device tracking + heartbeat | Agent visibility 100% |
| 3 | 3-4 | Nominatim reverse-geocoding | Quartiers 75% |
| 4 | 4-8 | Compass + IMU + Pedometer | Capteurs réels 100% |

### Phase 1 : Taux sync > 75%

**Coût :** 4 jours dev

**Changements :**
- `app_config.dart` : Backoff config (1s, 2s, 4s, 8s, 16s)
- `sync_service.dart` : Retry loop avec scheduleRetry() + NetworkService.isConnected()
- `server.py` : Idempotence (vérifier capture_id existant)
- `local_store.dart` : Table `sync_retries` (tracking tentatives)

**Résultat :**
- 0 perte capture (même 30s offline)
- 75%+ confirmés serveur (au lieu 25%)
- Backup automatique en FAILED_PERMANENT après 5 tentatives

### Phase 2 : Agent visibility

**Coût :** 5 jours dev

**Changements :**
- Domain : `Device` + `DeviceSession` aggregates
- Mobile : Heartbeat timer (chaque 30s) + GPS broadcast
- Server : `/api/devices/heartbeat` + `/api/map.geojson` (fusion agents+captures)
- Frontend : Agents EN LIGNE = cercle bleu (gros), détection timeout 60s

**Résultat :**
- Agents bleus visibles temps réel
- Coordinateurs voient qui est actif
- Mesh peer discovery : "Qui est près de moi?"

### Phase 3 : Quartiers

**Coût :** 4 jours dev

**Changements :**
- Backend : `NominatimCache` (reverse-geocoding avec cache 24h TTL)
- Mobile : `LocationService.getNeighborhoodName()` + show in label
- Frontend : Filter dropdown (Médina, Kouara, Zogona, etc.)
- Serve : `neighborhood` field dans GeoJSON features

**Résultat :**
- Toute capture taggée "Quartier Médina" etc.
- Front filtre par zone 1-click
- Reports administrative-ready

### Phase 4 : Capteurs réels

**Coût :** 10 jours dev

| Capteur | Coût | Status |
|---------|------|--------|
| Compass (heading) | 2j | `flutter_compass` + HUD |
| IMU (accel+gyro) | 3j | `sensors_plus` + spoofing check |
| Pedometer | 2j | `pedometer` + daily counter |
| Sync log UI | 3j | Detail sheet + retry attempts |

**Résultat :**
- IMU consistency score RÉEL (spoofing detectable)
- Trust scores basés multi-sensor (pas GPS seul)
- HUD affiche heading, acceleration, steps

---

## Architecture après MVP

```
Mobile (Flutter)
├─ LocalStore (SQLite)
│  ├─ captures table
│  ├─ sync_retries table   ← Phase 1
│  └─ device_heartbeats    ← Phase 2
├─ Services
│  ├─ GpsService (real-time stream + accuracy)
│  ├─ SyncService (retry logic + network detection)
│  ├─ CompassService (heading stream)           ← Phase 4
│  ├─ IMUService (accel+gyro fusion)            ← Phase 4
│  ├─ PedometerService (step count)             ← Phase 4
│  └─ LocationService (reverse-geocoding)       ← Phase 3
└─ UI
   ├─ Map (Leaflet + flutter_map)
   ├─ HUD (sensors + sync status)
   └─ SyncHistory (details + retries)           ← Phase 4

Server (Python DDD)
├─ Infrastructure
│  ├─ InMemoryRepository (captures)
│  ├─ DeviceSessionRepository                   ← Phase 2
│  └─ NominatimCache (neighborhoods)            ← Phase 3
├─ Domain
│  ├─ Capture (state machine: NEW → LOCAL → ... → ARCHIVED)
│  ├─ Device + DeviceSession aggregates         ← Phase 2
│  └─ Neighborhood value object                 ← Phase 3
└─ Presentation (HTTP)
   ├─ POST /api/captures (idempotent)           ← Phase 1
   ├─ POST /api/captures/{id}/sync
   ├─ POST /api/devices/heartbeat               ← Phase 2
   ├─ GET /api/devices                          ← Phase 2
   ├─ GET /api/map.geojson (agents + captures)  ← Phase 2
   └─ GET /api/events
```

---

## Checklist de déploiement

### Phase 1 (Semaines 1-2)

- [ ] `app_config.dart` : backoff config
- [ ] `sync_service.dart` : retry loop + network detection
- [ ] `local_store.dart` : sync_retries table
- [ ] `server.py` : idempotence check
- [ ] Test : 10 captures, offline 45s, puis online → tous synced
- [ ] Acceptation : Taux sync 75%+

### Phase 2 (Semaines 2-3)

- [ ] `device_info_plus` package
- [ ] Backend : Device + DeviceSession domain
- [ ] Backend : DeviceSessionRepository
- [ ] Mobile : Heartbeat timer + location broadcast
- [ ] Backend : `/api/devices/heartbeat` + `/api/devices`
- [ ] Backend : `/api/map.geojson` (fusion)
- [ ] Frontend : Marquer agents bleus
- [ ] Test : 2 agents simultanés → visibles, déconnexion → gris après 60s
- [ ] Acceptation : Agent visibility 100%

### Phase 3 (Semaines 3-4)

- [ ] `requests` package backend
- [ ] Backend : `NominatimCache` + reverse-geocoding
- [ ] Mobile : `LocationService` + quartier dans label
- [ ] Backend : `neighborhood` dans GeoJSON + Capture
- [ ] Frontend : Filter dropdown (dynamique)
- [ ] Test : 5 captures Ouaga → tous avec quartier identifié
- [ ] Acceptation : 95% quartiers identifiés

### Phase 4 (Semaines 4-8)

- [ ] `flutter_compass` package
- [ ] `sensors_plus` package
- [ ] `pedometer` package
- [ ] CompassService + HUD heading
- [ ] IMUService + spoofing detection
- [ ] PedometerService + daily counter
- [ ] SyncLog UI + detail sheet
- [ ] Test : IMU spoofing detect (throw phone = low score)
- [ ] Acceptation : Tous capteurs réels

---

## Budget & Coûts

| Ressource | Quantité | Coût |
|-----------|----------|------|
| Frontend dev | 1.5 semaines | 60h |
| Backend dev | 0.5 semaine | 20h |
| QA/Testing | 1 semaine | 40h |
| Infra (AWS t3.micro server) | 8 semaines | 60 USD |
| **Total** | — | **120h + 60 USD** |

**ROI :** Une fois > 75% sync, adoption terrain +150% (ex: 2 agents → 5 agents).

---

## Risques & Mitigations

| Risque | Mitigation |
|--------|-----------|
| Nominatim rate-limit | Cache 24h TTL ; fallback "Unknown Quartier" |
| Android permission denial | Clear onboarding (permissions required to function) |
| Network flaky (3G) | Backoff jitter (1s ±500ms) pour éviter thundering herd |
| Compass offset | User calibrate UI (1-2 figure-8 rotations) |
| Battery drain sensors | Sampling throttle : compass 1Hz, IMU 50ms, pedometer 1s |
| Heartbeat overload | Server-side connection pooling + async processing |

---

## Go/No-Go Criteria

**Go :** Si toutes phases 1-4 complètes + pass criteria:
- Taux sync > 75% (mesurable via snapshot JSON)
- Agent visibility tested (2 devices → visibles/invisible timeouts)
- Quartiers 95% accuracy (random 10 captures → tous taggés)
- Capteurs réels (compass ±5°, IMU spoofing detect, steps > 0)

**No-Go :** Si après phase 1 sync < 60% → architecture retry cassée.

---

## Prochaines étapes post-MVP

1. **Phase 5 (Semaines 9-10) :** PostGIS migration (in-memory → PostgreSQL)
2. **Phase 6 (Semaines 11-12) :** WebSocket temps réel (polling → push)
3. **Phase 7 (Semaines 13-16) :** Offline-first MBTiles hors-ligne
4. **Phase 8 (Semaines 17+) :** Multi-device mesh P2P (Bluetooth/NFC)

---

## Conclusion

MapNet a une **architecture solide (DDD)** mais manque **implémentation capteurs + retry strategy**. **MVP 8 semaines** résout tous les blockers critiques.

**État fin MVP :** 
- ✅ Taux sync 75%+ (capturesne se perdent jamais)
- ✅ Agents visibles (coordinateurs voient terrain en temps réel)
- ✅ Quartiers indexés (navigation géographique)
- ✅ Capteurs réels (données de qualité)

**Prêt pour production sur 50-100 agents terrain en Ouagadougou.**

---

**Documents de support :**
- `docs/diagnostic-problemes.md` — Détail technique des 6 problèmes
- `docs/mvp-feuille-route.md` — Plan MVP complet (code + changements)
- `docs/application-mobile.md` — Architecture mobile (existant)
- `docs/carte-serveur.md` — Architecture backend (existant)
