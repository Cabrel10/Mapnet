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

import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

class LocalDataSummary {
  const LocalDataSummary({
    required this.localVersion,
    required this.serverVersion,
    required this.lastSyncAt,
    required this.roadCount,
    required this.pendingTelemetryCount,
  });

  final int localVersion;
  final int serverVersion;
  final DateTime? lastSyncAt;
  final int roadCount;
  final int pendingTelemetryCount;

  bool get isCurrent => localVersion > 0 && localVersion >= serverVersion;
}

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
    await db
        .execute('CREATE INDEX idx_tel_sync ON local_telemetry(sync_status)');
  }

  Future<LocalDataSummary> getLocalSummary() async {
    final db = await database;
    final versions = await db.query(
      'sync_dataset',
      columns: ['local_version', 'server_version', 'last_sync_at'],
      where: 'dataset_name = ?',
      whereArgs: ['map'],
      limit: 1,
    );
    final roadRows = await db.rawQuery(
      'SELECT COUNT(*) AS total FROM local_road_attributes',
    );
    final telemetryRows = await db.rawQuery(
      'SELECT COUNT(*) AS total FROM local_telemetry WHERE sync_status != ?',
      [2],
    );

    final version = versions.isEmpty ? null : versions.first;
    final lastSyncMillis = version?['last_sync_at'] as int?;
    return LocalDataSummary(
      localVersion: version?['local_version'] as int? ?? 0,
      serverVersion: version?['server_version'] as int? ?? 0,
      lastSyncAt: lastSyncMillis == null
          ? null
          : DateTime.fromMillisecondsSinceEpoch(lastSyncMillis),
      roadCount: Sqflite.firstIntValue(roadRows) ?? 0,
      pendingTelemetryCount: Sqflite.firstIntValue(telemetryRows) ?? 0,
    );
  }
}
