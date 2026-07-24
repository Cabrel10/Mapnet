// MAPNET MOBILE — Modèle d'agrégat "Capture" (miroir mobile du domaine DDD).
import 'package:flutter/material.dart';

enum CaptureType {
  poi,
  roadDamage,
  voiceNote,
  photo;

  String get label {
    switch (this) {
      case CaptureType.poi:
        return 'Point d\'intérêt';
      case CaptureType.roadDamage:
        return 'Dégradation route';
      case CaptureType.voiceNote:
        return 'Note vocale';
      case CaptureType.photo:
        return 'Photo géoréférée';
    }
  }

  IconData get icon {
    switch (this) {
      case CaptureType.poi:
        return Icons.location_on;
      case CaptureType.roadDamage:
        return Icons.dangerous;
      case CaptureType.voiceNote:
        return Icons.graphic_eq;
      case CaptureType.photo:
        return Icons.photo_camera;
    }
  }

  static CaptureType fromName(String s) =>
      CaptureType.values.firstWhere((e) => e.name == s, orElse: () => CaptureType.poi);
}

class Capture {
  final String id;
  final double lat;
  final double lon;
  final CaptureType type;
  final double trustScore;
  final String syncState; // PENDING / SYNCING / SYNCED / FAILED_RETRY
  final DateTime createdAt;

  Capture({
    required this.id,
    required this.lat,
    required this.lon,
    required this.type,
    required this.trustScore,
    required this.syncState,
    required this.createdAt,
  });

  Map<String, dynamic> toMap() => {
        'id': id,
        'lat': lat,
        'lon': lon,
        'type': type.name,
        'trust_score': trustScore,
        'sync_state': syncState,
        'created_at': createdAt.toIso8601String(),
      };

  factory Capture.fromMap(Map<String, dynamic> m) => Capture(
        id: m['id'] as String,
        lat: (m['lat'] as num).toDouble(),
        lon: (m['lon'] as num).toDouble(),
        type: CaptureType.fromName(m['type'] as String),
        trustScore: (m['trust_score'] as num).toDouble(),
        syncState: m['sync_state'] as String,
        createdAt: DateTime.parse(m['created_at'] as String),
      );
}
