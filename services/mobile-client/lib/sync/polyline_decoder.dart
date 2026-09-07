// MAPNET
//
// Repository: github.com/Cabrel10/Mapnet
// Path: services/mobile-client/lib/sync/polyline_decoder.dart

import 'package:latlong2/latlong.dart';

class PolylineDecoder {
  /// Décode une chaîne de caractères encodée (format Google Polyline de PostGIS)
  /// en une liste de coordonnées géographiques (LatLng).
  static List<LatLng> decode(String encoded) {
    List<LatLng> points = [];
    int index = 0, len = encoded.length;
    int lat = 0, lng = 0;

    while (index < len) {
      int b, shift = 0, result = 0;
      do {
        b = encoded.codeUnitAt(index++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      int dlat = ((result & 1) != 0 ? ~(result >> 1) : (result >> 1));
      lat += dlat;

      shift = 0;
      result = 0;
      do {
        b = encoded.codeUnitAt(index++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      int dlng = ((result & 1) != 0 ? ~(result >> 1) : (result >> 1));
      lng += dlng;

      // Division par 1e5 conforme au standard d'encodage géospatiale
      points.add(LatLng(lat / 100000.0, lng / 100000.0));
    }
    return points;
  }
}
