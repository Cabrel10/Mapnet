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
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE captures (
            id TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            type TEXT NOT NULL,
            trust_score REAL NOT NULL,
            sync_state TEXT NOT NULL,
            created_at TEXT NOT NULL
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

  Future<void> _log(String level, String message) async {
    await _db!.insert('local_telemetry', {
      'ts': DateTime.now().toIso8601String(),
      'level': level,
      'message': message,
    });
  }

  /// Amorçage de démonstration autour d'un point d'origine (parité serveur DDD).
  Future<void> seedDemo(dynamic origin) async {
    final rnd = Random(42);
    final types = CaptureType.values;
    for (var i = 0; i < 8; i++) {
      final dLat = (rnd.nextDouble() - 0.5) * 0.06;
      final dLon = (rnd.nextDouble() - 0.5) * 0.06;
      final t = types[rnd.nextInt(types.length)];
      await insertCapture(Capture(
        id: 'seed_$i',
        lat: origin.latitude + dLat,
        lon: origin.longitude + dLon,
        type: t,
        trustScore: 0.3 + rnd.nextDouble() * 0.65,
        syncState: i % 3 == 0 ? 'SYNCED' : 'PENDING',
        createdAt: DateTime.now().subtract(Duration(minutes: i * 7)),
      ));
    }
  }
}
