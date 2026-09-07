import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:mapnet_mobile_client/navigation/navigation_math.dart';

void main() {
  group('NavigationMath', () {
    test('normalizes headings', () {
      expect(NavigationMath.normalizeHeading(-10), 350);
      expect(NavigationMath.normalizeHeading(725), 5);
    });

    test('measures proximity to route segments', () {
      const route = [LatLng(3.8480, 11.5000), LatLng(3.8480, 11.5040)];
      const point = LatLng(3.8481, 11.5020);

      final proximity = NavigationMath.closestRouteSegment(point, route);

      expect(proximity.segmentIndex, 0);
      expect(proximity.distanceM, lessThan(15));
    });

    test('confirms deviation and blocks reentrant or cooldown reroutes', () {
      final now = DateTime.utc(2026, 9, 2, 12);
      final started = NavigationMath.shouldReroute(
        distanceM: 90,
        accuracyM: 5,
        now: now,
        offRouteSince: null,
        lastRerouteAt: null,
        rerouting: false,
      );
      final confirmed = NavigationMath.shouldReroute(
        distanceM: 90,
        accuracyM: 5,
        now: now.add(const Duration(seconds: 4)),
        offRouteSince: started.offRouteSince,
        lastRerouteAt: null,
        rerouting: false,
      );
      final reentrant = NavigationMath.shouldReroute(
        distanceM: 90,
        accuracyM: 5,
        now: now.add(const Duration(seconds: 4)),
        offRouteSince: started.offRouteSince,
        lastRerouteAt: null,
        rerouting: true,
      );
      final cooldown = NavigationMath.shouldReroute(
        distanceM: 90,
        accuracyM: 5,
        now: now.add(const Duration(seconds: 4)),
        offRouteSince: started.offRouteSince,
        lastRerouteAt: now,
        rerouting: false,
      );

      expect(started.trigger, isFalse);
      expect(confirmed.trigger, isTrue);
      expect(reentrant.trigger, isFalse);
      expect(cooldown.trigger, isFalse);
    });
  });
}
