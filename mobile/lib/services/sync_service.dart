// MAPNET MOBILE — Synchronisation bidirectionnelle (DTN / Mesh).
//
// Corrige l'isolement réseau de la v1 : l'app n'envoyait rien au VPS et ne
// téléchargeait pas les points des autres agents. Ici on fait les DEUX sens :
//   PUSH : upload des captures locales PENDING vers POST /api/captures.
//   PULL : download de TOUTES les captures serveur (autres agents) -> carte.
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../database/local_store.dart';
import '../models/capture.dart';

class SyncOutcome {
  final bool online;
  final int pushed;
  final int pulled;
  final String? error;
  const SyncOutcome(
      {required this.online, this.pushed = 0, this.pulled = 0, this.error});
}

class SyncService {
  SyncService._();
  static final SyncService instance = SyncService._();

  final LocalStore _store = LocalStore.instance;
  Timer? _timer;

  /// Boucle périodique. `onResult` remonte l'état à l'UI (badge réseau).
  void start(void Function(SyncOutcome) onResult) {
    _timer?.cancel();
    // Premier passage immédiat, puis toutes les N secondes.
    syncOnce().then(onResult);
    _timer = Timer.periodic(
      const Duration(seconds: AppConfig.syncIntervalSeconds),
      (_) => syncOnce().then(onResult),
    );
  }

  void stop() => _timer?.cancel();

  /// Un cycle complet PUSH + PULL. Ne jette jamais : renvoie un SyncOutcome.
  Future<SyncOutcome> syncOnce() async {
    int pushed = 0;
    try {
      // ---- PUSH : captures locales non confirmées ----
      final pending = await _store.unsynced();
      for (final c in pending.where((c) => c.owner == 1)) {
        final ok = await _pushOne(c);
        if (ok) {
          await _store.markSynced(c.id);
          pushed++;
        } else {
          await _store.markState(c.id, 'FAILED_RETRY');
        }
      }

      // ---- PULL : captures de tous les agents ----
      final pulled = await _pullAll();

      return SyncOutcome(online: true, pushed: pushed, pulled: pulled);
    } on TimeoutException {
      return SyncOutcome(online: false, pushed: pushed, error: 'timeout');
    } catch (e) {
      return SyncOutcome(online: false, pushed: pushed, error: e.toString());
    }
  }

  Future<bool> _pushOne(Capture c) async {
    try {
      final res = await http
          .post(
            Uri.parse(AppConfig.capturesEndpoint),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'lat': c.lat,
              'lon': c.lon,
              'kind': c.serverKind,
              'label': c.type.label,
              'signals': {
                'accuracy_m': c.accuracyM,
                'trust_hint': c.trustScore,
                'source': 'mobile_field',
              },
            }),
          )
          .timeout(AppConfig.httpTimeout);
      return res.statusCode == 201 || res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Télécharge les captures serveur et les fond dans le store local (owner=0).
  Future<int> _pullAll() async {
    final res = await http
        .get(Uri.parse(AppConfig.capturesEndpoint))
        .timeout(AppConfig.httpTimeout);
    if (res.statusCode != 200) return 0;
    final decoded = jsonDecode(res.body);
    if (decoded is! List) return 0;

    // Ids déjà présents localement en tant que captures À NOUS -> on ne les
    // réécrase pas avec owner=0.
    final local = await _store.loadCaptures();
    final mineIds = local.where((c) => c.owner == 1).map((c) => c.id).toSet();

    int pulled = 0;
    for (final item in decoded) {
      if (item is! Map) continue;
      final srv = Capture.fromServer(Map<String, dynamic>.from(item));
      if (mineIds.contains(srv.id)) continue;
      await _store.upsertRemote(srv);
      pulled++;
    }
    return pulled;
  }
}
