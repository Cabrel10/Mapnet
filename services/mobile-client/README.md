# MapNet — Client Mobile (Offline-First / DTN)

Client terrain « Data Mule » conçu pour les zones à connectivité intermittente
(ex. Yaoundé hors-ligne). Conforme aux principes **Offline-First** et
**DTN (Delay-Tolerant Networking)** : l'appareil fonctionne totalement
déconnecté et ne synchronise qu'au retour d'un lien (Wi-Fi au dépôt).

Le composant critique stabilisé ici est le **Moteur de Synchronisation Client**,
et non l'intégralité de l'UI.

## Architecture du cycle de synchronisation

```
1. En déplacement (hors-ligne)
   └─ MbTilesManager lit yaounde.mbtiles (tuiles vectorielles locales)
   └─ Calcul d'itinéraires 100% local

2. Collecte passive
   └─ Traces GPS + anomalies -> SQLite (local_telemetry, local_road_attributes)

3. Retour au dépôt (Wi-Fi actif)
   └─ SyncManager.executeSync()
       ├─ GET /api/map/api/v1/sync/manifest   (version serveur)
       ├─ compare avec sync_dataset.local_version (modèle Git-like)
       ├─ GET /api/map/api/v1/sync/delta?since=<localVersion>
       ├─ PolylineDecoder.decode(geom_polyline)  (PostGIS -> LatLng)
       └─ transaction SQLite : applique A/M/D + met à jour la version locale
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `lib/sync/polyline_decoder.dart` | Décodage natif des polylines encodées (ST_AsEncodedPolyline) |
| `lib/sync/sync_manager.dart` | Synchronisation différentielle incrémentale (manifest → delta → SQLite) |
| `lib/sync/mbtiles_manager.dart` | Accès aux tuiles vectorielles MBTiles hors-ligne (axe Y TMS inversé) |
| `lib/database/db_helper.dart` | Schéma SQLite local (`sync_dataset`, `local_road_attributes`, `local_telemetry`) |

## Contrat Gateway (Go)

- `GET /api/map/api/v1/sync/manifest` → `{ "versions": { "map": <int> } }`
- `GET /api/map/api/v1/sync/delta?since=<int>` → `{ "head": <int>, "changes": [ { "edge_id", "change_type"(A|M|D), "geom_polyline", "highway_type", "is_oneway" } ] }`

## Résilience

Toute erreur réseau est absorbée silencieusement (`mode dégradé actif`) :
l'application reste utilisable hors-ligne et retentera la synchronisation au
prochain lien disponible.
