import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:latlong2/latlong.dart';
import 'package:mapnet_mobile_client/navigation/mapnet_api.dart';

void main() {
  group('MapNetApi.search', () {
    test('envoie la proximité et décode les lieux camerounais', () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/api/v1/places/search');
        expect(request.url.queryParameters, {
          'q': 'stade olembe',
          'limit': '5',
          'grouped': 'false',
          'lat': '3.848',
          'lon': '11.5021',
        });
        return http.Response(
          jsonEncode({
            'results': [
              {
                'id': 'poi-1',
                'name': "Stade d'Olembé",
                'kind': 'poi',
                'city': 'Yaoundé',
                'category': 'stade',
                'latitude': 3.9504,
                'longitude': 11.5408,
                'distance_m': 12142.3,
              },
            ],
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = MapNetApi(gatewayUrl: 'http://gateway.test/', client: client);

      final results = await api.search(
        ' stade olembe ',
        near: const LatLng(3.848, 11.5021),
        limit: 5,
      );

      expect(results, hasLength(1));
      expect(results.single.name, "Stade d'Olembé");
      expect(results.single.city, 'Yaoundé');
      expect(results.single.position.latitude, closeTo(3.9504, 0.000001));
      expect(results.single.position.longitude, closeTo(11.5408, 0.000001));
      expect(results.single.distanceM, closeTo(12142.3, 0.1));
      api.close();
    });

    test('rejette une réponse non conforme', () async {
      final api = MapNetApi(
        gatewayUrl: 'http://gateway.test',
        client: MockClient((_) async => http.Response('{}', 200)),
      );

      expect(
        () => api.search('Yaoundé'),
        throwsA(isA<NavigationException>()),
      );
      api.close();
    });
  });

  group('MapNetApi.navigate', () {
    test('envoie les coordonnées et décode GeoJSON et étapes', () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/route/api/v1/routing/navigate');
        expect(request.headers['content-type'], 'application/json');
        expect(jsonDecode(request.body), {
          'from_lat': 3.848,
          'from_lon': 11.5021,
          'to_lat': 3.9504,
          'to_lon': 11.5408,
        });
        return http.Response(
          jsonEncode({
            'status': 'ok',
            'route': {
              'distance': 17213.9,
              'duration': 1007.6,
              'geometry': {
                'type': 'LineString',
                'coordinates': [
                  [11.5021, 3.848],
                  [11.5408, 3.9504],
                ],
              },
              'steps': [
                {
                  'instruction': 'Tournez à droite',
                  'location': [11.51, 3.86],
                  'distance': 120.0,
                  'duration': 18.0,
                },
              ],
            },
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      final api = MapNetApi(gatewayUrl: 'http://gateway.test', client: client);

      final route = await api.navigate(
        from: const LatLng(3.848, 11.5021),
        to: const LatLng(3.9504, 11.5408),
      );

      expect(route.distanceM, closeTo(17213.9, 0.1));
      expect(route.durationS, closeTo(1007.6, 0.1));
      expect(route.distanceLabel, '17.2 km');
      expect(route.durationLabel, '17 min');
      expect(route.points, hasLength(2));
      expect(route.points.last.latitude, closeTo(3.9504, 0.000001));
      expect(route.steps.single.instruction, 'Tournez à droite');
      expect(route.steps.single.position.longitude, closeTo(11.51, 0.000001));
      api.close();
    });

    test('rejette un itinéraire sans géométrie', () async {
      final api = MapNetApi(
        gatewayUrl: 'http://gateway.test',
        client: MockClient(
          (_) async => http.Response(
            jsonEncode({
              'route': {
                'distance': 0,
                'duration': 0,
                'geometry': {'coordinates': <Object>[]},
                'steps': <Object>[],
              },
            }),
            200,
          ),
        ),
      );

      expect(
        () => api.navigate(
          from: const LatLng(3.848, 11.5021),
          to: const LatLng(3.9, 11.55),
        ),
        throwsA(isA<NavigationException>()),
      );
      api.close();
    });
  });
}
