// MAPNET MOBILE — Utilitaires géographiques (distance / cap).
// Sert la fonctionnalité "lieux à proximité" : trier les captures autour de
// la position réelle de l'utilisateur pour la navigation GPS de terrain.
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

class GeoUtils {
  static const double _earthRadiusM = 6371000.0;

  /// Distance haversine en mètres entre deux points.
  static double distanceMeters(LatLng a, LatLng b) {
    final dLat = _rad(b.latitude - a.latitude);
    final dLon = _rad(b.longitude - a.longitude);
    final la1 = _rad(a.latitude);
    final la2 = _rad(b.latitude);
    final h = math.sin(dLat / 2) * math.sin(dLat / 2) +
        math.cos(la1) * math.cos(la2) * math.sin(dLon / 2) * math.sin(dLon / 2);
    return 2 * _earthRadiusM * math.asin(math.min(1.0, math.sqrt(h)));
  }

  /// Cap (bearing) en degrés de a vers b (0 = Nord, sens horaire).
  static double bearingDeg(LatLng a, LatLng b) {
    final dLon = _rad(b.longitude - a.longitude);
    final la1 = _rad(a.latitude);
    final la2 = _rad(b.latitude);
    final y = math.sin(dLon) * math.cos(la2);
    final x = math.cos(la1) * math.sin(la2) -
        math.sin(la1) * math.cos(la2) * math.cos(dLon);
    final brng = _deg(math.atan2(y, x));
    return (brng + 360) % 360;
  }

  /// Distance minimale entre [point] et les segments de [route].
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
    final referenceLat = (point.latitude + start.latitude + end.latitude) / 3;
    const latitudeScale = math.pi * _earthRadiusM / 180;
    final longitudeScale =
        latitudeScale * math.cos(referenceLat * math.pi / 180);

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
    if (lengthSquared == 0) {
      return math.sqrt(
        math.pow(p.x - a.x, 2) + math.pow(p.y - a.y, 2),
      );
    }
    final rawT = ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared;
    final t = rawT.clamp(0.0, 1.0);
    final nearestX = a.x + t * dx;
    final nearestY = a.y + t * dy;
    return math.sqrt(
      math.pow(p.x - nearestX, 2) + math.pow(p.y - nearestY, 2),
    );
  }

  /// Confirme une déviation et applique précision GPS, cooldown et anti-réentrance.
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
    final effectiveThreshold =
        math.max(thresholdM, math.max(0.0, accuracyM) * 2).toDouble();
    if (!distanceM.isFinite || distanceM <= effectiveThreshold) {
      return RerouteDecision(
        trigger: false,
        offRouteSince: null,
        effectiveThresholdM: effectiveThreshold,
      );
    }
    final startedAt = offRouteSince ?? now;
    final confirmed = now.difference(startedAt) >= confirmation;
    final cooledDown =
        lastRerouteAt == null || now.difference(lastRerouteAt) >= cooldown;
    return RerouteDecision(
      trigger: confirmed && cooledDown && !rerouting,
      offRouteSince: startedAt,
      effectiveThresholdM: effectiveThreshold,
    );
  }

  /// Rose des vents FR à 8 directions.
  static String compass(double bearing) {
    const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'];
    return dirs[((bearing + 22.5) % 360 ~/ 45)];
  }

  static String humanDistance(double m) {
    if (m < 1000) return '${m.round()} m';
    return '${(m / 1000).toStringAsFixed(m < 10000 ? 1 : 0)} km';
  }

  static double _rad(double d) => d * math.pi / 180.0;
  static double _deg(double r) => r * 180.0 / math.pi;
}
