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
  final double accuracyM; // précision GPS réelle (m) au moment de la capture
  final int owner; // 1 = capturée par CET appareil, 0 = reçue d'un autre agent

  Capture({
    required this.id,
    required this.lat,
    required this.lon,
    required this.type,
    required this.trustScore,
    required this.syncState,
    required this.createdAt,
    this.accuracyM = 0,
    this.owner = 1,
  });

  Map<String, dynamic> toMap() => {
        'id': id,
        'lat': lat,
        'lon': lon,
        'type': type.name,
        'trust_score': trustScore,
        'sync_state': syncState,
        'created_at': createdAt.toIso8601String(),
        'accuracy_m': accuracyM,
        'owner': owner,
      };

  factory Capture.fromMap(Map<String, dynamic> m) => Capture(
        id: m['id'] as String,
        lat: (m['lat'] as num).toDouble(),
        lon: (m['lon'] as num).toDouble(),
        type: CaptureType.fromName(m['type'] as String),
        trustScore: (m['trust_score'] as num).toDouble(),
        syncState: m['sync_state'] as String,
        createdAt: DateTime.parse(m['created_at'] as String),
        accuracyM: (m['accuracy_m'] as num?)?.toDouble() ?? 0,
        owner: (m['owner'] as num?)?.toInt() ?? 1,
      );

  /// Décodage d'une capture serveur (schéma DDD backend : point{lat,lon,accuracy_m}).
  factory Capture.fromServer(Map<String, dynamic> j) {
    final pt = (j['point'] as Map?) ?? const {};
    final kind = (j['kind'] as String?) ?? 'poi';
    return Capture(
      id: (j['capture_id'] as String?) ?? (j['id'] as String?) ?? 'srv',
      lat: (pt['lat'] as num?)?.toDouble() ?? 0,
      lon: (pt['lon'] as num?)?.toDouble() ?? 0,
      type: _kindToType(kind),
      trustScore: (j['trust_score'] as num?)?.toDouble() ?? 0.5,
      syncState: 'SYNCED',
      createdAt: DateTime.fromMillisecondsSinceEpoch(
        (((j['created_at'] as num?)?.toDouble() ?? 0) * 1000).round(),
        isUtc: true,
      ),
      accuracyM: (pt['accuracy_m'] as num?)?.toDouble() ?? 0,
      owner: 0,
    );
  }

  /// Mapping type mobile -> `kind` attendu par le backend (POST /api/captures).
  String get serverKind {
    switch (type) {
      case CaptureType.roadDamage:
        return 'road_condition';
      case CaptureType.voiceNote:
        return 'voice_note';
      case CaptureType.photo:
        return 'photo';
      case CaptureType.poi:
        return 'poi';
    }
  }

  static CaptureType _kindToType(String kind) {
    switch (kind) {
      case 'road_condition':
        return CaptureType.roadDamage;
      case 'voice_note':
        return CaptureType.voiceNote;
      case 'photo':
        return CaptureType.photo;
      default:
        return CaptureType.poi;
    }
  }

  Capture copyWith({String? syncState}) => Capture(
        id: id,
        lat: lat,
        lon: lon,
        type: type,
        trustScore: trustScore,
        syncState: syncState ?? this.syncState,
        createdAt: createdAt,
        accuracyM: accuracyM,
        owner: owner,
      );
}
