# MapNet Mobile Android

Application Flutter offline-first pour les agents terrain à Yaoundé.

## Fonctions livrées

- capture GPS physique et stockage SQLite local ;
- boussole, accéléromètre, gyroscope et pédomètre physiques ;
- HUD transparent : une mesure absente reste indisponible ;
- synchronisation PUSH/PULL avec détection réseau et probe `/health` ;
- retry exponentiel persistant (60, 120, 240, 480 secondes), puis dead-letter à la cinquième erreur ;
- historique des erreurs et date du prochain retry ;
- heartbeat d'appareil toutes les 30 secondes ;
- quartier résolu par le backend Nominatim et conservé localement.

Aucune donnée capteur de démonstration n'est générée dans l'application.

## Configuration serveur

La valeur par défaut est `http://169.58.67.16:8088`. Elle peut être remplacée au build :

```bash
flutter build apk --debug \
  --dart-define=MAPNET_SERVER=http://serveur:8088
```

## Validation et build

```bash
flutter pub get
flutter test
flutter analyze
flutter build apk --debug
```

APK universel : `build/app/outputs/flutter-apk/app-debug.apk`.

L'APK debug est signé avec la clé Android debug et peut être installé avec :

```bash
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

Les permissions de localisation et de reconnaissance d'activité sont demandées à l'exécution. Les capteurs déclarés sont optionnels : l'application continue de fonctionner sur un appareil qui n'en possède pas et ne présente pas de valeur synthétique.
