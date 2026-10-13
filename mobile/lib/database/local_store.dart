// MAPNET MOBILE — Persistance locale SQLite (Offline-First / DTN).
// Table transactionnelle `captures` : source de vérité hors-ligne du terminal.
import 'dart:math';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

import '../models/capture.dart';

class LocalStore {
  LocalStore._();
  static final LocalStore instance = LocalStore._();

  Database? _db;

  Future<void> init() async {
    if (_db != null) return;
    final dir = await getApplicationDocumentsDirectory();
    final path = p.join(dir.path, 'mapnet_terrain.db');
    _db = await openDatabase(
      path,
      version: 4,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE captures (
            id TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            type TEXT NOT NULL,
            trust_score REAL NOT NULL,
            sync_state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            accuracy_m REAL NOT NULL DEFAULT 0,
            owner INTEGER NOT NULL DEFAULT 1,
            sync_retries INTEGER NOT NULL DEFAULT 0,
            next_retry_at TEXT,
            last_sync_error TEXT,
            neighborhood TEXT,
            speed_ms REAL,
            course_deg REAL,
            sensor_json TEXT NOT NULL DEFAULT '{}'
          )
        ''');
        await db.execute('''
          CREATE TABLE local_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
          )
        ''');
      },
      onUpgrade: (db, oldV, newV) async {
        if (oldV < 2) {
          await db.execute(
              'ALTER TABLE captures ADD COLUMN accuracy_m REAL NOT NULL DEFAULT 0');
          await db.execute(
              'ALTER TABLE captures ADD COLUMN owner INTEGER NOT NULL DEFAULT 1');
        }
        if (oldV < 3) {
          await db.execute(
              'ALTER TABLE captures ADD COLUMN sync_retries INTEGER NOT NULL DEFAULT 0');
          await db
              .execute('ALTER TABLE captures ADD COLUMN next_retry_at TEXT');
          await db
              .execute('ALTER TABLE captures ADD COLUMN last_sync_error TEXT');
          await db.execute('ALTER TABLE captures ADD COLUMN neighborhood TEXT');
          await db.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
          ''');
        }
        if (oldV < 4) {
          await db.execute('ALTER TABLE captures ADD COLUMN speed_ms REAL');
          await db.execute('ALTER TABLE captures ADD COLUMN course_deg REAL');
          await db.execute(
              "ALTER TABLE captures ADD COLUMN sensor_json TEXT NOT NULL DEFAULT '{}'");
        }
      },
    );
  }

  Future<void> insertCapture(Capture c) async {
    await _db!.insert('captures', c.toMap(),
        conflictAlgorithm: ConflictAlgorithm.replace);
    await _log('INFO', 'Capture ${c.id} (${c.type.name}) stockée hors-ligne');
  }

  Future<List<Capture>> loadCaptures() async {
    if (_db == null) await init();
    final rows = await _db!.query('captures', orderBy: 'created_at DESC');
    return rows.map(Capture.fromMap).toList();
  }

  /// Captures locales pas encore confirmées par le serveur (à uploader).
  Future<List<Capture>> unsynced() async {
    if (_db == null) await init();
    final rows = await _db!.query(
      'captures',
      where: "owner = 1 AND sync_state NOT IN (?, ?) AND "
          "(next_retry_at IS NULL OR next_retry_at <= ?)",
      whereArgs: ['SYNCED', 'DEAD_LETTER', DateTime.now().toIso8601String()],
      orderBy: 'created_at ASC',
    );
    return rows.map(Capture.fromMap).toList();
  }

  Future<void> markSynced(String id) async {
    await _db!.update(
        'captures',
        {
          'sync_state': 'SYNCED',
          'sync_retries': 0,
          'next_retry_at': null,
          'last_sync_error': null,
        },
        where: 'id = ?',
        whereArgs: [id]);
    await _log('INFO', 'Capture $id confirmée par le serveur');
  }

  Future<void> markState(String id, String state) async {
    await _db!.update('captures', {'sync_state': state},
        where: 'id = ?', whereArgs: [id]);
  }

  Future<void> updateNeighborhood(String id, String? neighborhood) async {
    if (neighborhood == null || neighborhood.isEmpty) return;
    await _db!.update(
      'captures',
      {'neighborhood': neighborhood},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> recordRetry({
    required String id,
    required int retries,
    required String error,
    required DateTime? nextRetryAt,
    required bool deadLetter,
  }) async {
    await _db!.update(
      'captures',
      {
        'sync_state': deadLetter ? 'DEAD_LETTER' : 'FAILED_RETRY',
        'sync_retries': retries,
        'next_retry_at': nextRetryAt?.toIso8601String(),
        'last_sync_error': error,
      },
      where: 'id = ?',
      whereArgs: [id],
    );
    await _log(
      deadLetter ? 'ERROR' : 'WARN',
      deadLetter
          ? 'Capture $id en dead-letter après $retries tentatives: $error'
          : 'Capture $id tentative $retries, prochain essai ${nextRetryAt?.toIso8601String()}: $error',
    );
  }

  Future<String> getOrCreateDeviceId() async {
    if (_db == null) await init();
    final rows = await _db!.query(
      'app_settings',
      columns: ['value'],
      where: 'key = ?',
      whereArgs: ['device_id'],
      limit: 1,
    );
    if (rows.isNotEmpty) return rows.first['value'] as String;
    final random = Random.secure();
    final id =
        'android_${DateTime.now().microsecondsSinceEpoch.toRadixString(16)}_'
        '${random.nextInt(1 << 32).toRadixString(16)}';
    await _db!.insert('app_settings', {'key': 'device_id', 'value': id});
    return id;
  }

  Future<List<Map<String, dynamic>>> syncHistory({int limit = 100}) async {
    if (_db == null) await init();
    return _db!.query(
      'local_telemetry',
      orderBy: 'id DESC',
      limit: limit,
    );
  }

  /// Insère/actualise une capture provenant du serveur (download, autres agents).
  /// Marquée SYNCED car elle est déjà côté serveur — évite un renvoi en boucle.
  Future<void> upsertRemote(Capture c) async {
    await _db!.insert('captures', c.toMap(),
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> _log(String level, String message) async {
    await _db!.insert('local_telemetry', {
      'ts': DateTime.now().toIso8601String(),
      'level': level,
      'message': message,
    });
  }
}
