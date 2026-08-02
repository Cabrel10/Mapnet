// MAPNET MOBILE — Service de géolocalisation temps réel.
//
// Corrige la faute d'ergonomie de la v1 : la précision GPS n'était plus une
// valeur codée en dur (4.2 m), elle provient du capteur réel. Fournit :
//   - une demande de permissions runtime interactive (Android 10+) ;
//   - un point courant à la demande (bouton capture) ;
//   - un flux continu de positions (live tracking / centrage carte).
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';

enum GpsPermissionResult { granted, denied, deniedForever, serviceDisabled }

class GpsService {
  GpsService._();
  static final GpsService instance = GpsService._();

  /// Demande interactive des permissions au lancement.
  /// Gère les 3 issues : accordé / refusé / refusé définitivement.
  Future<GpsPermissionResult> ensurePermissions() async {
    // 1) Le service de localisation de l'appareil est-il activé ?
    final serviceOn = await Geolocator.isLocationServiceEnabled();
    if (!serviceOn) return GpsPermissionResult.serviceDisabled;

    // 2) Permission applicative (modale système).
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever) {
      return GpsPermissionResult.deniedForever;
    }
    if (perm == LocationPermission.denied) {
      return GpsPermissionResult.denied;
    }

    // 3) Stockage (SQLite / cache tuiles) — non bloquant si refusé.
    await Permission.storage.request();

    return GpsPermissionResult.granted;
  }

  /// Ouvre les réglages de l'app (cas refus définitif).
  Future<void> openSettings() => openAppSettings();

  /// Position ponctuelle haute précision (déclenchée par le bouton capture).
  Future<Position> current() {
    return Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.best,
      timeLimit: const Duration(seconds: 15),
    );
  }

  /// Flux continu : se déclenche tous les ~5 m de déplacement.
  Stream<Position> stream() {
    return Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 5,
      ),
    );
  }

  /// HDOP approximé depuis la précision horizontale (m). Le plugin ne remonte
  /// pas le DOP brut ; on dérive un proxy exploitable pour le HUD terrain.
  static double hdopFromAccuracy(double accuracyMeters) {
    if (accuracyMeters <= 0) return 0;
    // ~5 m d'incertitude ≈ HDOP 1.0 (convention pragmatique).
    return (accuracyMeters / 5.0).clamp(0.5, 50.0);
  }
}
