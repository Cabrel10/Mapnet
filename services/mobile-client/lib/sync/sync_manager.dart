// MAPNET
//
// Synchronisation différentielle du client Data Mule.

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';

import '../database/db_helper.dart';
import 'polyline_decoder.dart';

class SyncResult {
  const SyncResult({
    required this.success,
    required this.localVersion,
    required this.serverVersion,
    required this.appliedChanges,
    required this.completedAt,
    this.error,
  });

  final bool success;
  final int localVersion;
  final int serverVersion;
  final int appliedChanges;
  final DateTime completedAt;
  final String? error;

  bool get isUpToDate => success && localVersion >= serverVersion;
}

class SyncManager {
  SyncManager({required String gatewayUrl, http.Client? client})
      : gatewayUrl = gatewayUrl.replaceFirst(RegExp(r'/+$'), ''),
        _client = client ?? http.Client();

  final String gatewayUrl;
  final http.Client _client;
  final DatabaseHelper dbHelper = DatabaseHelper.instance;

  static const Duration _requestTimeout = Duration(seconds: 20);

  /// Exécute la synchronisation différentielle incrémentale.
  ///
  /// Une erreur réseau n'interrompt jamais l'application : elle est retournée
  /// à l'interface afin que l'agent sache que le mode hors-ligne reste actif.
  Future<SyncResult> executeSync() async {
    final db = await dbHelper.database;
    var localVersion = 0;
    var serverVersion = 0;

    try {
      final versionRows = await db.query(
        'sync_dataset',
        columns: ['local_version'],
        where: 'dataset_name = ?',
        whereArgs: ['map'],
        limit: 1,
      );
      if (versionRows.isNotEmpty) {
        localVersion = versionRows.first['local_version'] as int? ?? 0;
      }

      final manifestResponse = await _client
          .get(Uri.parse('$gatewayUrl/api/map/api/v1/sync/manifest'))
          .timeout(_requestTimeout);
      if (manifestResponse.statusCode != 200) {
        throw Exception('manifest HTTP ${manifestResponse.statusCode}');
      }

      final manifest = jsonDecode(manifestResponse.body);
      if (manifest is! Map<String, dynamic> ||
          manifest['versions'] is! Map<String, dynamic> ||
          (manifest['versions'] as Map<String, dynamic>)['map'] is! num) {
        throw const FormatException('manifest MAPNET invalide');
      }
      serverVersion =
          ((manifest['versions'] as Map<String, dynamic>)['map'] as num)
              .toInt();

      if (localVersion >= serverVersion) {
        final completedAt = DateTime.now();
        await _upsertVersion(
          db,
          localVersion: localVersion,
          serverVersion: serverVersion,
          completedAt: completedAt,
        );
        return SyncResult(
          success: true,
          localVersion: localVersion,
          serverVersion: serverVersion,
          appliedChanges: 0,
          completedAt: completedAt,
        );
      }

      final deltaResponse = await _client
          .get(Uri.parse(
            '$gatewayUrl/api/map/api/v1/sync/delta?since=$localVersion',
          ))
          .timeout(_requestTimeout);
      if (deltaResponse.statusCode != 200) {
        throw Exception('delta HTTP ${deltaResponse.statusCode}');
      }

      final delta = jsonDecode(deltaResponse.body);
      if (delta is! Map<String, dynamic> ||
          delta['changes'] is! List<dynamic> ||
          delta['head'] is! num) {
        throw const FormatException('delta MAPNET invalide');
      }
      final changes = delta['changes'] as List<dynamic>;
      final headVersion = (delta['head'] as num).toInt();
      final completedAt = DateTime.now();

      await db.transaction((txn) async {
        for (final rawChange in changes) {
          if (rawChange is! Map<String, dynamic>) {
            throw const FormatException('entrée de delta invalide');
          }
          final edgeId = rawChange['edge_id']?.toString();
          final changeType = rawChange['change_type']?.toString();
          if (edgeId == null || edgeId.isEmpty) {
            throw const FormatException('edge_id absent');
          }

          if (changeType == 'D') {
            await txn.delete(
              'local_road_attributes',
              where: 'attribute_id = ?',
              whereArgs: [edgeId],
            );
            continue;
          }
          if (changeType != 'A' && changeType != 'M') {
            throw FormatException('change_type inconnu: $changeType');
          }

          final encodedPolyline = rawChange['geom_polyline']?.toString() ?? '';
          final points = PolylineDecoder.decode(encodedPolyline);
          if (points.isEmpty) {
            throw FormatException('géométrie vide pour $edgeId');
          }

          await txn.insert(
            'local_road_attributes',
            {
              'attribute_id': edgeId,
              'trip_id': 'sync_import',
              'latitude': points.first.latitude,
              'longitude': points.first.longitude,
              'road_type': rawChange['highway_type'] ?? 'piste',
              'is_oneway': rawChange['is_oneway'] == true ? 1 : 0,
              'pavement_condition': 'good',
              'road_status': 'open',
              'recorded_at': completedAt.millisecondsSinceEpoch,
              'sync_status': 2,
            },
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }

        await txn.insert(
          'sync_dataset',
          {
            'dataset_name': 'map',
            'local_version': headVersion,
            'server_version': serverVersion,
            'last_sync_at': completedAt.millisecondsSinceEpoch,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
      });

      return SyncResult(
        success: true,
        localVersion: headVersion,
        serverVersion: serverVersion,
        appliedChanges: changes.length,
        completedAt: completedAt,
      );
    } catch (error) {
      return SyncResult(
        success: false,
        localVersion: localVersion,
        serverVersion: serverVersion,
        appliedChanges: 0,
        completedAt: DateTime.now(),
        error: error.toString(),
      );
    }
  }

  Future<void> _upsertVersion(
    Database db, {
    required int localVersion,
    required int serverVersion,
    required DateTime completedAt,
  }) {
    return db.insert(
      'sync_dataset',
      {
        'dataset_name': 'map',
        'local_version': localVersion,
        'server_version': serverVersion,
        'last_sync_at': completedAt.millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  void close() => _client.close();
}
