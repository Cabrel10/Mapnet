// MAPNET
//
// Repository: github.com/Cabrel10/Mapnet
// Path: services/mobile-client/lib/sync/sync_manager.dart

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';
import '../database/db_helper.dart';
import 'polyline_decoder.dart';

class SyncManager {
  final String gatewayUrl; // Adresse de la Go Gateway (ex: https://api.mapnet.local)
  final DatabaseHelper dbHelper = DatabaseHelper.instance;

  SyncManager({required this.gatewayUrl});

  /// Exécute la synchronisation différentielle incrémentale
  Future<void> executeSync() async {
    final db = await dbHelper.database;

    try {
      // 1. Interroger le manifest de la Gateway pour connaître la version serveur
      final manifestResponse = await http.get(Uri.parse('$gatewayUrl/api/map/api/v1/sync/manifest'));
      if (manifestResponse.statusCode != 200) throw Exception("Échec de récupération du manifest");

      final Map<String, dynamic> manifest = json.decode(manifestResponse.body);
      final int serverVersion = manifest['versions']['map'];

      // 2. Récupérer la version locale stockée dans SQLite
      final List<Map<String, dynamic>> versionResult = await db.query(
        'sync_dataset',
        where: "dataset_name = 'map'"
      );

      int localVersion = 0;
      if (versionResult.isNotEmpty) {
        localVersion = versionResult.first['local_version'] as int;
      } else {
        // Initialisation de la version de la carte en base locale
        await db.insert('sync_dataset', {
          'dataset_name': 'map',
          'local_version': 0,
          'server_version': serverVersion,
          'last_sync_at': DateTime.now().millisecondsSinceEpoch
        });
      }

      // 3. Comparer les versions (Modèle Git-like)
      if (localVersion >= serverVersion) {
        // La carte locale est déjà à jour, arrêt du processus
        return;
      }

      // 4. Télécharger uniquement le delta d'arêtes depuis la version locale
      final deltaResponse = await http.get(
        Uri.parse('$gatewayUrl/api/map/api/v1/sync/delta?since=$localVersion')
      );
      if (deltaResponse.statusCode != 200) throw Exception("Échec de téléchargement du delta");

      final Map<String, dynamic> deltaData = json.decode(deltaResponse.body);
      final List<dynamic> changes = deltaData['changes'];
      final int newHeadVersion = deltaData['head'];

      // 5. Appliquer les modifications en base locale SQLite (Transaction)
      await db.transaction((txn) async {
        for (var change in changes) {
          final String edgeId = change['edge_id'];
          final String changeType = change['change_type']; // "A" (Ajout), "M" (Modification), "D" (Suppression)

          if (changeType == 'D') {
            // Suppression de l'arête locale
            await txn.delete(
              'local_road_attributes',
              where: 'attribute_id = ?',
              whereArgs: [edgeId]
            );
          } else {
            // Décodage de la géométrie compressée
            final String encodedPolyline = change['geom_polyline'];
            final points = PolylineDecoder.decode(encodedPolyline);

            // Insertion ou mise à jour de l'arête avec sa géométrie décodée
            await txn.insert(
              'local_road_attributes',
              {
                'attribute_id': edgeId,
                'trip_id': 'sync_import',
                'latitude': points.first.latitude,
                'longitude': points.first.longitude,
                'road_type': change['highway_type'] ?? 'piste',
                'is_oneway': change['is_oneway'] == true ? 1 : 0,
                'pavement_condition': 'good',
                'road_status': 'open',
                'recorded_at': DateTime.now().millisecondsSinceEpoch,
                'sync_status': 2 // Marqué comme synchronisé
              },
              conflictAlgorithm: ConflictAlgorithm.replace
            );
          }
        }

        // 6. Mettre à jour le numéro de version local
        await txn.update(
          'sync_dataset',
          {
            'local_version': newHeadVersion,
            'server_version': serverVersion,
            'last_sync_at': DateTime.now().millisecondsSinceEpoch
          },
          where: "dataset_name = 'map'"
        );
      });

    } catch (e) {
      // Gestion silencieuse des erreurs réseau (DTN - Résilience déconnectée)
      print("Erreur de synchronisation MAPNET (mode dégradé actif) : $e");
    }
  }
}
