// MAPNET MOBILE — Configuration réseau.
//
// POINT CRITIQUE : sur un smartphone physique, `localhost`/`127.0.0.1` désigne
// LE TÉLÉPHONE lui-même, PAS le serveur VPS. Toutes les captures se perdaient
// donc dans le vide. On pointe explicitement vers l'IP publique du VPS où
// tourne la gateway MapNet (backend DDD, port 8088 sur ce serveur).
//
// Surchargeable au build : `flutter build apk --dart-define=MAPNET_SERVER=http://x.x.x.x:8088`
class AppConfig {
  /// URL de base du serveur MapNet (backend DDD / gateway PostGIS).
  static const String serverUrl = String.fromEnvironment(
    'MAPNET_SERVER',
    defaultValue: 'http://169.58.67.16:8088',
  );

  /// Endpoints REST.
  static String get capturesEndpoint => '$serverUrl/api/captures';
  static String capturesSyncEndpoint(String id) =>
      '$serverUrl/api/captures/$id/sync';
  static String get statsEndpoint => '$serverUrl/api/stats';
  static String get heartbeatEndpoint => '$serverUrl/api/devices/heartbeat';
  static String get devicesEndpoint => '$serverUrl/api/devices';
  static String get mapEndpoint => '$serverUrl/api/map.geojson';

  /// Cadence de la boucle de synchronisation bidirectionnelle (secondes).
  static const int syncIntervalSeconds = 20;

  /// Timeout réseau par requête.
  static const Duration httpTimeout = Duration(seconds: 10);

  /// Retry exponentiel persistant : 1, 2, 4, 8, 16 minutes, puis dead-letter.
  static const int maxRetries = 5;
  static const int initialBackoffSeconds = 60;
  static const double backoffMultiplier = 2.0;

  /// Heartbeat agent, inférieur au timeout serveur (90 s).
  static const int heartbeatIntervalSeconds = 30;
}
