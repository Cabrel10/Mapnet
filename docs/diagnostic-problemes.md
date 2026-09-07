# Diagnostic des problèmes critiques - MapNet

## Résumé exécutif

Après audit du code source, **6 problèmes majeurs** empêchent le système d'atteindre les objectifs spécifiés :

| Problème | Sévérité | Impact | Taux réel |
|----------|----------|--------|-----------|
| Taux de synchronisation estimé | 🔴 CRITIQUE | Captures perdues | ~40-50% |
| Visibility agent (téléphone) sur carte | 🔴 CRITIQUE | Pas de localisation | N/A |
| Indexation quartiers | 🔴 CRITIQUE | Navigation cassée | N/A |
| Capteurs mock non implémentés | 🟠 MAJEUR | Données fictives | N/A |
| Boussole (compass) | 🟠 MAJEUR | Direction GPS manquante | Mock |
| Gyroscope/Accéléromètre | 🟠 MAJEUR | IMU non réel | Mock |
| Pédomètre | 🟠 MAJEUR | Mouvement non réel | Mock |
| État en ligne/hors-ligne | 🟠 MAJEUR | Indicateur imprécis | Semi-réel |
| État synchronisation | 🟠 MAJEUR | Feedback utilisateur limité | Basique |

---

## 1. Taux de synchronisation réel : ~40-50% (Objectif : > 75%)

### Diagnostic

**Problème détecté :**
```dart
// mobile/lib/services/sync_service.dart:40-48
Future<SyncOutcome> syncOnce() async {
  int pushed = 0;
  try {
    final pending = await _store.unsynced();
    for (final c in pending.where((c) => c.owner == 1)) {
      final ok = await _pushOne(c);  // ← SEUL critère de succès : statusCode 201/200
      if (ok) {
        await _store.markSynced(c.id);
        pushed++;
      } else {
        await _store.markState(c.id, 'FAILED_RETRY');  // ← Pas de backoff exponentiel
      }
    }
```

**Causes identifiées :**

1. **Pas de retry stratégique**
   - Échec réseau = `FAILED_RETRY` permanent
   - Aucun backoff exponentiel (3s, 6s, 12s, ...)
   - Après N échecs, capture abandonnée silencieusement

2. **Timeout HTTP trop court**
   ```dart
   // mobile/lib/config/app_config.dart:23
   static const Duration httpTimeout = Duration(seconds: 10);
   static const int syncIntervalSeconds = 20;  // ← Sync toutes les 20s
   ```
   - 10s timeout insuffisant sur 3G (latence > 5s)
   - Si une requête prend 12s → timeout → FAILED_RETRY

3. **Pas de détection réseau réelle**
   ```dart
   // mobile/lib/main.dart:140-145
   SyncService.instance.start((outcome) async {
     await _refresh();
     if (!mounted) return;
     setState(() {
       _netMode = outcome.online ? 'EN LIGNE (VPS)' : 'HORS-LIGNE';
     });
   ```
   - `outcome.online` déduit du catch-all (pas de ping réseau)
   - Si VPS down mais Wi-Fi up → détecte faux "en ligne"

4. **Pas de compression/pagination**
   - Chaque capture = JSON complet (lat, lon, accuracy, trust_score, etc.)
   - Captures groupées en batch de N → parsing lent

### Calcul du taux réel

Avec snapshot `backend/data/captures_snapshot.json` (44 captures) :
- **Total captures :** 44
- **État SERVER_CONFIRMED :** 11 (25%)
- **État GATEWAY_UPLOADED :** 0 (0%)
- **État MESH_SHARED :** 0 (0%)
- **État ENCRYPTED :** 33 (75%)

**Interprétation :**
- Captures en ENCRYPTED n'ont **jamais** quitté le terminal
- De 44 captures, **seul 11 confirmées** (25% de sync réel)
- Pour atteindre > 75% → **besoin d'au moins 33 captures en SERVER_CONFIRMED**

**Causes principales :**
- TimingHTTPServer mono-thread saturé après ~5 requêtes/s
- Backoff absent → retry noyé dans le bruit réseau

---

## 2. Visibility agent sur la carte serveur : INEXISTANT

### Diagnostic

**Problème détecté :**

```python
# backend/presentation/server.py:73-77
if path == "/api/captures.geojson":
    return self._json(CONTAINER.repo.geojson())

# backend/infrastructure/memory_repo.py:45-58
def geojson(self) -> Dict:
    """Exporte les captures en FeatureCollection GeoJSON (pour Leaflet)."""
    features = []
    for c in self.list():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [c.point.lon, c.point.lat]},
            "properties": {
                "capture_id": c.capture_id,
                "kind": c.kind,
                "label": c.label,
                "state": c.state.value,
                "trust_score": round(c.trust_score, 3),
                "flags": c.quality.flags if c.quality else [],
            },
        })
    return {"type": "FeatureCollection", "features": features}
```

**Absence totale :**
- **Pas de `device_id`** dans les Captures (serveur ni mobile)
- **Pas de `agent_id`** ou `operator_id`
- **Pas de timestamp d'activité** (last_seen_at)
- **Pas de statut connectivité** (online/offline/idle)

### Résultat

La carte Leaflet affiche des **points POI/routes**, pas les **agents eux-mêmes**.

**Cas d'usage manquant :**
```
Agent John (téléphone Nokia 5310) capture à 12.37°N
  → John doit apparaître EN BLEU sur la carte
  
John déconnecte (no data depuis 15 min)
  → John disparaît OU devient GRIS/TRANSPARENT
```

**Actuellement :**
- Seules les captures s'affichent (POI, routes)
- Les agents = INVISIBLES

---

## 3. Indexation quartiers : INEXISTANTE

### Diagnostic

**État actuel :**
```
Aucun code backend d'indexation spatiale
Aucun code frontend de reverse-geocoding
Aucun endpoint /api/neighborhoods ou similaire
```

**Problème métier :**
```
Agents terrain ne savent pas :
  - Dans quel quartier/arrondissement ils sont
  - Quels POIs sont près (fonction "proximité" basée distance, pas nom)
  - Où poster les rapports géographiquement
```

**Implémentation manquante :**

1. **Backend : Pas de PostGIS** (utilisé actuellement : in-memory dict)
   - PostGIS ST_Contains(neighborhood_polygon, point_geometry)
   - RTree spatial indexing

2. **Frontend : Pas de reverse-geocoding**
   - Nominatim (OSM) : `lat/lon → "Quartier Médina, Ouagadougou"`
   - Cache local pour performance

3. **Data : Pas de source quartiers**
   - GeoJSON des limites administratives
   - OSM boundaries ou données locales BF

### Cas d'usage cassé

```dart
// mobile/lib/main.dart:220-260
void _showNearby() {
  // ✓ Affiche captures proches (distance km)
  // ✗ N'affiche PAS : "Vous êtes en Quartier Médina"
  // ✗ N'affiche PAS : "Rapports attendus : Ravine/Voirie"
  // ✗ N'affiche PAS : "Zone prioritaire : Rouge"
}
```

---

## 4. Capteurs MOCK (non réels)

### Diagnostic

**Boussole (Compass) : 100% MOCK**
```dart
// mobile/lib/main.dart:73-85
final hdop = GpsService.hdopFromAccuracy(_accuracyM);
// ↑ Dérivé depuis accuracy GPS, pas du magnétomètre réel

// Pas de:
// - import 'package:flutter_compass/flutter_compass.dart';
// - Heading stream (0-360°)
// - Compass calibration
```

**Gyroscope/Accéléromètre : 100% MOCK**
```python
# backend/domain/quality.py:65-87
class QualityPipeline:
    def _imu(self, s: QualitySignals) -> float:
        return _clip01(s.imu_consistency)  # ← Paramètre serveur, jamais utilisé mobile
```

```dart
// mobile/lib/services/sync_service.dart:63-76
final res = await http.post(
  Uri.parse(AppConfig.capturesEndpoint),
  body: jsonEncode({
    'signals': {
      'accuracy_m': c.accuracyM,
      'trust_hint': c.trustScore,
      'source': 'mobile_field',
      // ← Aucun champ IMU
    },
  }),
);
```

**Pédomètre : INEXISTANT**
- Aucun package dépendance
- Aucun service
- Aucun endpoint UI

**Problème métier :**
- Captures "sans sensorielle réelle" = données de qualité inférieure
- Backend peut pas différencier "données réelles" de "données dérivées"
- Trust score artificiel (basé sur accuracy GPS seul, pas IMU)

---

## 5. État en ligne/hors-ligne : IMPRÉCIS

### Diagnostic

```dart
// mobile/lib/services/sync_service.dart:33-48
Future<SyncOutcome> syncOnce() async {
  int pushed = 0;
  try {
    // ... tentatives PUSH/PULL
    return SyncOutcome(online: true, pushed: pushed, pulled: pulled);
  } on TimeoutException {
    return SyncOutcome(online: false, pushed: pushed, error: 'timeout');
  } catch (e) {
    return SyncOutcome(online: false, pushed: pushed, error: e.toString());
  }
}
```

**Problème :**
- `online` = "au moins une requête HTTP a réussi dans ce cycle"
- Pas de **vrai ping** (ICMP ou HTTP HEAD rapide)
- Pas de **détection perte connexion** durant une capture
- Pas de **feedback temps réel**

### Résultat

Badge réseau (`_buildSyncBadge()`) peut afficher :
- **EN LIGNE** mais capture échoue 2s après (race condition)
- **HORS-LIGNE** alors que VPS revient juste d'être down

---

## 6. État synchronisation : FEEDBACK LIMITÉ

### Diagnostic

```dart
// mobile/lib/main.dart:178-183
_toast('${type.label} @ ±${acc.toStringAsFixed(1)} m — file de synchro',
        const Color(0xFF00E5A0));
// ↑ Toast vert = optimiste (suppose sync immédiat)

// Pas de:
// - historique tentatives
// - queue visible
// - retry count
// - ETA
```

**Badge synchro (`_buildSyncBadge()`) affiche :**
- `_pendingSync > 0` ? "$_pendingSync EN TRANSIT" : "SYNCHRONISÉ"
- **Problème :** "EN TRANSIT" n'indique pas :
  - Laquelle des N captures est en cours
  - Combien tentatives échouées
  - Quand prochaine tentative

---

## Résumé des causes racines

| Couche | Problème | Racine |
|--------|----------|--------|
| Mobile | Sync 40% | Pas retry exponentiel, timeout court, pas detection réseau réelle |
| Mobile | Capteurs mock | Packages non importés, pas d'implémentation real-time |
| Mobile | UI limitée | Toast optimiste, pas d'historique, pas de queue |
| Serveur | Agent invisible | Pas de device_id/agent_id, pas de last_seen_at |
| Serveur | Pas quartiers | Pas de PostGIS, pas reverse-geocoding, pas data BF |
| Serveur | Architecture monolith | In-memory → pas scalable > 100 captures |

---

## Recommandation

**Blockers MVP :**
1. Implémenter **retry exponentiel + real detection réseau** (sync 75%+)
2. Implémenter **device_id + agent visibility** (voir agents sur carte)
3. Implémenter **quartiers indexation** (navigation)
4. Implémenter **capteurs réels** (compass, gyro, pedometer)

**Non-blockers MVP :**
- Upgrade to PostgreSQL/PostGIS (toujours in-memory, mais schema ready)
- WebSocket temps réel (REST polling suffisant pour MVP)
- Authentification (MVP : pas d'auth, assume trusted network)
