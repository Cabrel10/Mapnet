import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

class NavigationException implements Exception {
  const NavigationException(this.message);

  final String message;

  @override
  String toString() => message;
}

class PlaceResult {
  const PlaceResult({
    required this.id,
    required this.name,
    required this.kind,
    required this.city,
    required this.position,
    this.category,
    this.distanceM,
  });

  final String id;
  final String name;
  final String kind;
  final String city;
  final LatLng position;
  final String? category;
  final double? distanceM;

  factory PlaceResult.fromJson(Map<String, dynamic> json) {
    return PlaceResult(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Lieu sans nom',
      kind: json['kind']?.toString() ?? 'place',
      city: json['city']?.toString() ?? '',
      position: LatLng(
        (json['latitude'] as num).toDouble(),
        (json['longitude'] as num).toDouble(),
      ),
      category: json['category']?.toString(),
      distanceM: (json['distance_m'] as num?)?.toDouble(),
    );
  }
}

class NavigationStep {
  const NavigationStep({
    required this.instruction,
    required this.position,
    required this.distanceM,
    required this.durationS,
  });

  final String instruction;
  final LatLng position;
  final double distanceM;
  final double durationS;

  factory NavigationStep.fromJson(Map<String, dynamic> json) {
    final location = json['location'] as List<dynamic>? ?? const [];
    return NavigationStep(
      instruction: json['instruction']?.toString() ?? 'Continuez',
      position: LatLng(
        location.length > 1 ? (location[1] as num).toDouble() : 0,
        location.isNotEmpty ? (location[0] as num).toDouble() : 0,
      ),
      distanceM: (json['distance'] as num?)?.toDouble() ?? 0,
      durationS: (json['duration'] as num?)?.toDouble() ?? 0,
    );
  }
}

class NavigationRoute {
  const NavigationRoute({
    required this.distanceM,
    required this.durationS,
    required this.points,
    required this.steps,
  });

  final double distanceM;
  final double durationS;
  final List<LatLng> points;
  final List<NavigationStep> steps;

  String get distanceLabel => distanceM >= 1000
      ? '${(distanceM / 1000).toStringAsFixed(1)} km'
      : '${distanceM.round()} m';

  String get durationLabel {
    final minutes = (durationS / 60).round();
    if (minutes >= 60) {
      return '${minutes ~/ 60} h ${minutes % 60} min';
    }
    return '$minutes min';
  }
}

class MapNetApi {
  MapNetApi({required String gatewayUrl, http.Client? client})
      : gatewayUrl = gatewayUrl.replaceFirst(RegExp(r'/+$'), ''),
        _client = client ?? http.Client();

  final String gatewayUrl;
  final http.Client _client;

  static const _timeout = Duration(seconds: 20);

  Future<List<PlaceResult>> search(
    String query, {
    LatLng? near,
    int limit = 20,
  }) async {
    final trimmed = query.trim();
    if (trimmed.length < 2) return const [];
    final params = <String, String>{
      'q': trimmed,
      'limit': '$limit',
      'grouped': 'false',
      if (near != null) 'lat': '${near.latitude}',
      if (near != null) 'lon': '${near.longitude}',
    };
    final uri = Uri.parse('$gatewayUrl/api/v1/places/search')
        .replace(queryParameters: params);
    final response = await _client.get(uri).timeout(_timeout);
    if (response.statusCode != 200) {
      throw NavigationException('Recherche indisponible (${response.statusCode})');
    }
    final body = jsonDecode(response.body);
    if (body is! Map<String, dynamic> || body['results'] is! List<dynamic>) {
      throw const NavigationException('Réponse de recherche invalide');
    }
    return (body['results'] as List<dynamic>)
        .whereType<Map<String, dynamic>>()
        .map(PlaceResult.fromJson)
        .toList();
  }

  Future<NavigationRoute> navigate({
    required LatLng from,
    required LatLng to,
  }) async {
    final uri = Uri.parse('$gatewayUrl/api/route/api/v1/routing/navigate');
    final response = await _client
        .post(
          uri,
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({
            'from_lat': from.latitude,
            'from_lon': from.longitude,
            'to_lat': to.latitude,
            'to_lon': to.longitude,
          }),
        )
        .timeout(_timeout);
    if (response.statusCode != 200) {
      throw NavigationException('Itinéraire indisponible (${response.statusCode})');
    }
    final body = jsonDecode(response.body);
    if (body is! Map<String, dynamic> || body['route'] is! Map<String, dynamic>) {
      throw const NavigationException('Réponse d’itinéraire invalide');
    }
    final route = body['route'] as Map<String, dynamic>;
    final geometry = route['geometry'] as Map<String, dynamic>?;
    final coordinates = geometry?['coordinates'] as List<dynamic>? ?? const [];
    final steps = route['steps'] as List<dynamic>? ?? const [];
    final points = coordinates
        .whereType<List<dynamic>>()
        .where((point) => point.length >= 2)
        .map((point) => LatLng(
              (point[1] as num).toDouble(),
              (point[0] as num).toDouble(),
            ))
        .toList();
    if (points.isEmpty) {
      throw const NavigationException('Géométrie d’itinéraire vide');
    }
    return NavigationRoute(
      distanceM: (route['distance'] as num?)?.toDouble() ?? 0,
      durationS: (route['duration'] as num?)?.toDouble() ?? 0,
      points: points,
      steps: steps
          .whereType<Map<String, dynamic>>()
          .map(NavigationStep.fromJson)
          .toList(),
    );
  }

  void close() => _client.close();
}
