import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:mapnet_mobile/services/geo_utils.dart';

void main() {
  group('GeoUtils navigation', () {
    test('measures distance to a route segment instead of its vertices', () {
      const route = [LatLng(3.8480, 11.5000), LatLng(3.8480, 11.5040)];
      const point = LatLng(3.8481, 11.5020);

      final proximity = GeoUtils.closestRouteSegment(point, route);

      expect(proximity.segmentIndex, 0);
      expect(proximity.distanceM, lessThan(15));
    });

    test('requires confirmation before rerouting', () {
      final startedAt = DateTime.utc(2026, 9, 2, 12);
      final first = GeoUtils.shouldReroute(
        distanceM: 90,
        accuracyM: 5,
        now: startedAt,
        offRouteSince: null,
        lastRerouteAt: null,
        rerouting: false,
      );
      final confirmed = GeoUtils.shouldReroute(
        distanceM: 90,
        accuracyM: 5,
        now: startedAt.add(const Duration(seconds: 4)),
        offRouteSince: first.offRouteSince,
        lastRerouteAt: null,
        rerouting: false,
      );

      expect(first.trigger, isFalse);
      expect(confirmed.trigger, isTrue);
    });

    test('adapts threshold to GPS accuracy and enforces cooldown', () {
      final now = DateTime.utc(2026, 9, 2, 12);
      final inaccurate = GeoUtils.shouldReroute(
        distanceM: 90,
        accuracyM: 50,
        now: now,
        offRouteSince: now.subtract(const Duration(seconds: 10)),
        lastRerouteAt: null,
        rerouting: false,
      );
      final coolingDown = GeoUtils.shouldReroute(
        distanceM: 120,
        accuracyM: 5,
        now: now,
        offRouteSince: now.subtract(const Duration(seconds: 10)),
        lastRerouteAt: now.subtract(const Duration(seconds: 5)),
        rerouting: false,
      );

      expect(inaccurate.effectiveThresholdM, 100);
      expect(inaccurate.trigger, isFalse);
      expect(coolingDown.trigger, isFalse);
    });
  });
}
