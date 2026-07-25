// MAPNET MOBILE — Configuration réseau.
//
// POINT CRITIQUE : sur un smartphone physique, `localhost`/`127.0.0.1` désigne
// LE TÉLÉPHONE lui-même, PAS le serveur VPS. Toutes les captures se perdaient
// donc dans le vide. On pointe explicitement vers l'IP publique du VPS où
// tourne la gateway MapNet (backend DDD, port 8080).
//
// Surchargeable au build : `flutter build apk --dart-define=MAPNET_SERVER=http://x.x.x.x:8080`
class AppConfig {
  /// URL de base du serveur MapNet (backend DDD / gateway PostGIS).
  static const String serverUrl = String.fromEnvironment(
    'MAPNET_SERVER',
    defaultValue: 'http://169.58.67.16:8080',
  );

  /// Endpoints REST.
  static String get capturesEndpoint => '$serverUrl/api/captures';
  static String capturesSyncEndpoint(String id) =>
      '$serverUrl/api/captures/$id/sync';
  static String get statsEndpoint => '$serverUrl/api/stats';

  /// Cadence de la boucle de synchronisation bidirectionnelle (secondes).
  static const int syncIntervalSeconds = 20;

  /// Timeout réseau par requête.
  static const Duration httpTimeout = Duration(seconds: 10);
}
