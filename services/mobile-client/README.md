# MapNet Navigation — Android client

Application Android de navigation pour les clients MapNet, distincte de
**MapNet Terrain**, l'application de collecte réservée aux agents.

## Navigation client

- carte plein écran centrée sur la position GPS réelle ;
- recherche Cameroun unifiée (quartiers, lieux et bâtiments) ;
- résultats classés par pertinence et proximité ;
- sélection d'une destination par recherche ou appui long sur la carte ;
- calcul d'itinéraire via le moteur MapNet ;
- tracé, distance, durée et instructions de guidage en français ;
- suivi de position et progression dans les étapes ;
- recentrage GPS et arrêt/reprise de la navigation.

## Mode hors-ligne

L'onglet **Hors-ligne** conserve le moteur Data Mule :

- versions carte locale/serveur ;
- routes SQLite et télémétries en attente ;
- synchronisation différentielle manifest → delta ;
- erreurs réseau visibles sans bloquer les données locales.

## Configuration Gateway

La Gateway par défaut est `http://169.58.67.16:8080`. Elle peut être remplacée
au build :

```bash
flutter build apk --release \
  --dart-define=MAPNET_GATEWAY=http://serveur:8080
```

Endpoints utilisés :

- `GET /api/v1/places/search`
- `POST /api/route/api/v1/routing/navigate`
- `GET /api/map/api/v1/sync/manifest`
- `GET /api/map/api/v1/sync/delta?since=<version>`

## Validation et build

```bash
flutter pub get
flutter test
flutter analyze
flutter build apk --release
```

APK universel : `build/app/outputs/flutter-apk/app-release.apk`.

L'APK est signé avec la clé Android debug afin d'être installable directement
hors store. Un keystore de publication dédié reste requis avant publication sur
Google Play.
