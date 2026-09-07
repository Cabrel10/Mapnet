// =============================================================================
// MAPNET MOBILE — Service d'itinéraire guidé (position -> destination).
//
// Interroge le serveur DDD (8088) qui proxifie le moteur de routage OSRM via
// le gateway Go. Contrat stable côté serveur :
//   POST /api/routing/navigate  {from_lat,from_lon,to_lat,to_lon}
//     -> { status, route: { distance, duration, geometry(LineString), steps[] } }
//   POST /api/position          {agent_id,lat,lon,accuracy,...}  -> tracking
//   GET  /api/agents            -> { agents: [...] }
//
// Offline-first cohérent avec le reste de l'app : si le serveur est
// injoignable, on lève une RoutingException et l'UI affiche un toast clair.
// =============================================================================
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

import '../config/app_config.dart';

class RoutingException implements Exception {
  RoutingException(this.message);
  final String message;
  @override
  String toString() => 'RoutingException: $message';
}

/// Une étape de navigation (manoeuvre OSRM traduite côté serveur).
class NavStep {
  NavStep({
    required this.instruction,
    required this.maneuver,
    required this.modifier,
    required this.location, // LatLng du point de manoeuvre
    required this.distanceM,
    required this.durationS,
  });

  final String instruction;
  final String maneuver;
  final String modifier;
  final LatLng location;
  final double distanceM;
  final double durationS;

  factory NavStep.fromJson(Map<String, dynamic> j) {
    final loc = (j['location'] as List?) ?? const [0.0, 0.0];
    return NavStep(
      instruction: (j['instruction'] ?? '') as String,
      maneuver: (j['maneuver'] ?? '') as String,
      modifier: (j['modifier'] ?? '') as String,
      location: LatLng(
        (loc.length > 1 ? (loc[1] as num).toDouble() : 0.0),
        (loc.isNotEmpty ? (loc[0] as num).toDouble() : 0.0),
      ),
      distanceM: (j['distance'] as num?)?.toDouble() ?? 0.0,
      durationS: (j['duration'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

/// Un itinéraire complet prêt pour la navigation.
class NavRoute {
  NavRoute({
    required this.distanceM,
    required this.durationS,
    required this.points, // polyline décodée (LatLng)
    required this.steps,
  });

  final double distanceM;
  final double durationS;
  final List<LatLng> points;
  final List<NavStep> steps;

  String get distanceLabel =>
      distanceM >= 1000 ? '${(distanceM / 1000).toStringAsFixed(1)} km' : '${distanceM.round()} m';
  String get durationLabel {
    final min = (durationS / 60).round();
    return min >= 60 ? '${min ~/ 60} h ${min % 60} min' : '$min min';
  }
}

class RoutingService {
  RoutingService._();
  static final RoutingService instance = RoutingService._();

  String get _navigateUrl => '${AppConfig.serverUrl}/api/routing/navigate';
  String get _positionUrl => '${AppConfig.serverUrl}/api/position';

  /// Calcule l'itinéraire de [from] vers [to]. Lève [RoutingException] si le
  /// serveur est hors-ligne ou ne trouve pas de route.
  Future<NavRoute> navigate({required LatLng from, required LatLng to}) async {
    http.Response resp;
    try {
      resp = await http
          .post(
            Uri.parse(_navigateUrl),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'from_lat': from.latitude,
              'from_lon': from.longitude,
              'to_lat': to.latitude,
              'to_lon': to.longitude,
            }),
          )
          .timeout(AppConfig.httpTimeout);
    } on TimeoutException {
      throw RoutingException('serveur injoignable (timeout)');
    } catch (e) {
      throw RoutingException('serveur injoignable ($e)');
    }

    if (resp.statusCode != 200) {
      throw RoutingException('erreur serveur ${resp.statusCode}');
    }

    Map<String, dynamic> data;
    try {
      data = jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      throw RoutingException('réponse invalide');
    }
    if (data['status'] != 'ok' || data['route'] == null) {
      throw RoutingException((data['error'] ?? 'aucun itinéraire').toString());
    }

    final r = data['route'] as Map<String, dynamic>;
    final coords =
        ((r['geometry']?['coordinates']) as List?)?.cast<List>() ?? const [];

    return NavRoute(
      distanceM: (r['distance'] as num?)?.toDouble() ?? 0.0,
      durationS: (r['duration'] as num?)?.toDouble() ?? 0.0,
      points: coords
          .map((c) => LatLng(
                (c.length > 1 ? (c[1] as num).toDouble() : 0.0),
                (c.isNotEmpty ? (c[0] as num).toDouble() : 0.0),
              ))
          .toList(),
      steps: ((r['steps'] as List?) ?? const [])
          .map((s) => NavStep.fromJson((s as Map).cast<String, dynamic>()))
          .toList(),
    );
  }

  /// Remonte la position live de l'agent au serveur (best-effort, jamais
  /// bloquant pour l'UX — une erreur réseau est silencieusement ignorée).
  Future<void> reportPosition({
    required String agentId,
    required LatLng pos,
    double? accuracyM,
    double? speedKmh,
    double? bearing,
  }) async {
    try {
      await http
          .post(
            Uri.parse(_positionUrl),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'agent_id': agentId,
              'lat': pos.latitude,
              'lon': pos.longitude,
              if (accuracyM != null) 'accuracy': accuracyM,
              if (speedKmh != null) 'speed_kmh': speedKmh,
              if (bearing != null) 'bearing': bearing,
              'timestamp': DateTime.now().toUtc().toIso8601String(),
            }),
          )
          .timeout(const Duration(seconds: 5));
    } catch (_) {
      // best-effort : l'envoi de position ne doit jamais casser la navigation
    }
  }
}
