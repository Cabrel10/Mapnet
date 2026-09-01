import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

class RouteProximity {
  const RouteProximity({required this.distanceM, required this.segmentIndex});

  final double distanceM;
  final int segmentIndex;
}

class RerouteDecision {
  const RerouteDecision({
    required this.trigger,
    required this.offRouteSince,
    required this.effectiveThresholdM,
  });

  final bool trigger;
  final DateTime? offRouteSince;
  final double effectiveThresholdM;
}

class NavigationMath {
  static const double _earthRadiusM = 6371000;

  static double normalizeHeading(double value) => (value % 360 + 360) % 360;

  static RouteProximity closestRouteSegment(
    LatLng point,
    List<LatLng> route,
  ) {
    if (route.isEmpty) {
      return const RouteProximity(
        distanceM: double.infinity,
        segmentIndex: 0,
      );
    }
    if (route.length == 1) {
      return RouteProximity(
        distanceM: pointToSegmentDistanceM(point, route.first, route.first),
        segmentIndex: 0,
      );
    }
    var bestDistance = double.infinity;
    var bestIndex = 0;
    for (var index = 0; index < route.length - 1; index++) {
      final distance = pointToSegmentDistanceM(
        point,
        route[index],
        route[index + 1],
      );
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    }
    return RouteProximity(distanceM: bestDistance, segmentIndex: bestIndex);
  }

  static double pointToSegmentDistanceM(
    LatLng point,
    LatLng start,
    LatLng end,
  ) {
    final referenceLat =
        (point.latitude + start.latitude + end.latitude) / 3;
    final latitudeScale = math.pi * _earthRadiusM / 180;
    final longitudeScale = latitudeScale * math.cos(referenceLat * math.pi / 180);

    ({double x, double y}) project(LatLng value) => (
          x: value.longitude * longitudeScale,
          y: value.latitude * latitudeScale,
        );

    final p = project(point);
    final a = project(start);
    final b = project(end);
    final dx = b.x - a.x;
    final dy = b.y - a.y;
    final lengthSquared = dx * dx + dy * dy;
    if (lengthSquared == 0) return math.sqrt(math.pow(p.x - a.x, 2) + math.pow(p.y - a.y, 2));
    final rawT = ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared;
    final t = rawT.clamp(0.0, 1.0);
    final nearestX = a.x + t * dx;
    final nearestY = a.y + t * dy;
    return math.sqrt(
      math.pow(p.x - nearestX, 2) + math.pow(p.y - nearestY, 2),
    );
  }

  static RerouteDecision shouldReroute({
    required double distanceM,
    required double accuracyM,
    required DateTime now,
    required DateTime? offRouteSince,
    required DateTime? lastRerouteAt,
    required bool rerouting,
    double thresholdM = 60,
    Duration confirmation = const Duration(seconds: 4),
    Duration cooldown = const Duration(seconds: 20),
  }) {
    final effectiveThreshold = math.max(thresholdM, math.max(0, accuracyM) * 2);
    if (!distanceM.isFinite || distanceM <= effectiveThreshold) {
      return RerouteDecision(
        trigger: false,
        offRouteSince: null,
        effectiveThresholdM: effectiveThreshold,
      );
    }
    final startedAt = offRouteSince ?? now;
    final confirmed = now.difference(startedAt) >= confirmation;
    final cooledDown = lastRerouteAt == null || now.difference(lastRerouteAt) >= cooldown;
    return RerouteDecision(
      trigger: confirmed && cooledDown && !rerouting,
      offRouteSince: startedAt,
      effectiveThresholdM: effectiveThreshold,
    );
  }
}
