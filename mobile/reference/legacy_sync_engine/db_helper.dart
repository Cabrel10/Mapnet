// MAPNET
//
// Repository: github.com/Cabrel10/Mapnet
// Path: services/mobile-client/lib/database/db_helper.dart
//
// Base SQLite locale du client mobile (Offline-First / DTN).
// Schéma minimal supportant le Moteur de Synchronisation :
//   - sync_dataset          : versions locales/serveur par jeu de données (map, ...)
//   - local_road_attributes : arêtes de voirie synchronisées + collectées
//   - local_telemetry       : traces GPS collectées passivement sur le terrain

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';

class DatabaseHelper {
  static const _dbName = 'mapnet_local.db';
  static const _dbVersion = 1;

  DatabaseHelper._privateConstructor();
  static final DatabaseHelper instance = DatabaseHelper._privateConstructor();

  static Database? _database;

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDatabase();
    return _database!;
  }

  Future<Database> _initDatabase() async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, _dbName);
    return await openDatabase(
      path,
      version: _dbVersion,
      onCreate: _onCreate,
    );
  }

  Future<void> _onCreate(Database db, int version) async {
    // Suivi de version par jeu de données (modèle Git-like).
    await db.execute('''
      CREATE TABLE sync_dataset (
        dataset_name   TEXT PRIMARY KEY,
        local_version  INTEGER NOT NULL DEFAULT 0,
        server_version INTEGER NOT NULL DEFAULT 0,
        last_sync_at   INTEGER
      )
    ''');

    // Arêtes de voirie (résultat du delta serveur + collecte terrain).
    await db.execute('''
      CREATE TABLE local_road_attributes (
        attribute_id       TEXT PRIMARY KEY,
        trip_id            TEXT,
        latitude           REAL,
        longitude          REAL,
        road_type          TEXT,
        is_oneway          INTEGER DEFAULT 0,
        pavement_condition TEXT,
        road_status        TEXT,
        recorded_at        INTEGER,
        sync_status        INTEGER DEFAULT 0
      )
    ''');

    // Télémétrie GPS brute collectée passivement (Data Mule).
    await db.execute('''
      CREATE TABLE local_telemetry (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id      TEXT,
        latitude     REAL,
        longitude    REAL,
        speed_ms     REAL,
        accuracy_m   REAL,
        recorded_at  INTEGER,
        sync_status  INTEGER DEFAULT 0
      )
    ''');

    await db.execute(
        'CREATE INDEX idx_road_sync ON local_road_attributes(sync_status)');
    await db.execute(
        'CREATE INDEX idx_tel_sync ON local_telemetry(sync_status)');
  }
}
