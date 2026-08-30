# MAPNET — Ports et adresses des services (169.58.67.16)

## Architecture des interfaces web
| Interface | URL | Rôle |
|-----------|-----|------|
| **Production** | http://169.58.67.16:8088/ | Backend DDD + carte de production (entrée unique de l'APK mobile) |
| **Debug** | http://169.58.67.16:8080/mapnet.html | Gateway + carte de debug (tests pipeline, logs) |

## Services backend
| Port | Service | Techno | Endpoints clés |
|------|---------|--------|----------------|
| 8080 | gateway | Go | `/api/gps/*` → 8095, `/api/map/*` → 8096, `/api/route/*` → 8093 |
| 8088 | backend DDD | Python stdlib | `/api/captures`, `/api/routing/navigate`, `/api/position`, `/api/agents` |
| 8093 | routing | FastAPI/OSRM | `/api/v1/routing/navigate`, `/route`, `/nearest`, `/health` |
| 8095 | gps-collect | Go | `/api/v1/collecte/gpx/upload`, `/api/v1/collecte/position`, `/api/v1/positions` |
| 8096 | map-engine | Go | `/api/v1/map/edges.geojson`, `/api/v1/sync/manifest`, `/health` |
| 9092 | Kafka | — | topic `quamtechs.mapnet.gps.raw` |
| 5432 | Postgres/PostGIS | — | DB `quamtechs_db` (tables: mapnet_edges, gpx_traces, agent_positions) |
| 8099 | distribution APK | http.server | `mapnet-terrain-v1.1.0.apk` et `mapnet-data-mule-v1.1.0.apk` |

## Notes
- Données carto seedées depuis OSM (zone Yaoundé) : `scripts/seed_edges_osm.sh`
- Géoloc navigateur : HTTPS requis — en HTTP utiliser « Position par clic ».
- APK Terrain : `http://169.58.67.16:8099/mapnet-terrain-v1.1.0.apk`.
- APK Data Mule : `http://169.58.67.16:8099/mapnet-data-mule-v1.1.0.apk`.
