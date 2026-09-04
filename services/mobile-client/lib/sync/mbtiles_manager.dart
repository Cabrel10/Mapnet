// MAPNET
//
// Repository: github.com/Cabrel10/Mapnet
// Path: services/mobile-client/lib/sync/mbtiles_manager.dart

import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

class MbTilesManager {
  static Database? _mbtilesDatabase;

  /// Initialise la connexion à la base de données de tuiles vectorielles locale (.mbtiles)
  Future<Database> get database async {
    if (_mbtilesDatabase != null) return _mbtilesDatabase!;
    _mbtilesDatabase = await _initMbTiles();
    return _mbtilesDatabase!;
  }

  Future<Database> _initMbTiles() async {
    final directory = await getApplicationDocumentsDirectory();
    final path = "${directory.path}/yaounde.mbtiles";

    // Vérification de la présence du fichier de base
    if (!await File(path).exists()) {
      throw Exception(
          "Fichier de tuiles yaounde.mbtiles introuvable. Veuillez exécuter une synchronisation Wi-Fi.");
    }

    return await openDatabase(path, readOnly: true);
  }

  /// Récupère une tuile de données vectorielles (PBF/MVT) depuis le stockage local
  Future<List<int>?> getTile(int z, int x, int y) async {
    final db = await database;

    // Le format MBTiles stocke l'axe Y de manière inversée (standard TMS)
    int tmsY = ((1 << z) - 1) - y;

    final List<Map<String, dynamic>> results = await db.query(
      'tiles',
      columns: ['tile_data'],
      where: 'zoom_level = ? AND tile_column = ? AND tile_row = ?',
      whereArgs: [z, x, tmsY],
    );

    if (results.isNotEmpty) {
      return results.first['tile_data'] as List<int>;
    }
    return null;
  }
}
