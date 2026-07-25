// MAPNET MOBILE — Utilitaires géographiques (distance / cap).
// Sert la fonctionnalité "lieux à proximité" : trier les captures autour de
// la position réelle de l'utilisateur pour la navigation GPS de terrain.
import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

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
