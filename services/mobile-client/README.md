# MapNet Data Mule — Android offline-first

Application Android Flutter dédiée à la synchronisation différentielle de la
carte MapNet dans les zones à connectivité intermittente.

## Fonctions livrées

- tableau de bord local : versions carte/serveur, routes, télémétries en attente ;
- état de connectivité explicite, sans bloquer l'utilisation hors-ligne ;
- synchronisation manuelle manifest → delta via la Gateway Go ;
- application transactionnelle des changements A/M/D dans SQLite ;
- affichage des erreurs réseau réelles et maintien automatique du mode dégradé ;
- accès aux tuiles locales `yaounde.mbtiles` via `MbTilesManager`.

## Configuration Gateway

La Gateway par défaut est `http://169.58.67.16:8080`. Elle peut être remplacée
au build :

```bash
flutter build apk --release \
  --dart-define=MAPNET_GATEWAY=http://serveur:8080
```

Contrat utilisé :

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

L'APK de terrain est actuellement signé avec la clé Android debug afin d'être
installable directement. Un keystore de publication dédié reste requis avant
diffusion sur un store.
