// MAPNET MOBILE — Synchronisation fiable PUSH/PULL + heartbeat.
import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../database/local_store.dart';
import '../models/capture.dart';
import 'sync_retry_policy.dart';

class SyncOutcome {
  final bool online;
  final int pushed;
  final int pulled;
  final int attempted;
  final int deadLettered;
  final DateTime? nextRetryAt;
  final String? error;

  const SyncOutcome({
    required this.online,
    this.pushed = 0,
    this.pulled = 0,
    this.attempted = 0,
    this.deadLettered = 0,
    this.nextRetryAt,
    this.error,
  });
}

class _PushResult {
  final bool ok;
  final String? error;
  const _PushResult(this.ok, [this.error]);
}

class SyncService {
  SyncService._();
  static final SyncService instance = SyncService._();

  final LocalStore _store = LocalStore.instance;
  Timer? _syncTimer;
  Timer? _heartbeatTimer;
  bool _busy = false;
  String? _deviceId;
  final String _sessionId =
      'session_${DateTime.now().millisecondsSinceEpoch}_${Random.secure().nextInt(1 << 32)}';
  double? _lat;
  double? _lon;
  double? _accuracyM;
  Map<String, dynamic> _sensors = const {};

  void updatePresence({
    required double lat,
    required double lon,
    required double accuracyM,
    Map<String, dynamic>? sensors,
  }) {
    _lat = lat;
    _lon = lon;
    _accuracyM = accuracyM;
    if (sensors != null) _sensors = sensors;
  }

  void start(void Function(SyncOutcome) onResult) {
    _syncTimer?.cancel();
    _heartbeatTimer?.cancel();
    syncOnce().then(onResult);
    _syncTimer = Timer.periodic(
      const Duration(seconds: AppConfig.syncIntervalSeconds),
      (_) => syncOnce().then(onResult),
    );
    _heartbeatTimer = Timer.periodic(
      const Duration(seconds: AppConfig.heartbeatIntervalSeconds),
      (_) => sendHeartbeat(),
    );
  }

  void stop() {
    _syncTimer?.cancel();
    _heartbeatTimer?.cancel();
  }

  Future<bool> _hasRealNetwork() async {
    final links = await Connectivity().checkConnectivity();
    if (links.isEmpty ||
        links.every((item) => item == ConnectivityResult.none)) {
      return false;
    }
    try {
      final response = await http
          .get(Uri.parse('${AppConfig.serverUrl}/health'))
          .timeout(AppConfig.httpTimeout);
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<SyncOutcome> syncOnce() async {
    if (_busy) {
      return const SyncOutcome(online: false, error: 'sync_already_running');
    }
    _busy = true;
    int pushed = 0;
    int attempted = 0;
    int deadLettered = 0;
    DateTime? nextRetry;
    try {
      if (!await _hasRealNetwork()) {
        return const SyncOutcome(online: false, error: 'network_unreachable');
      }
      await sendHeartbeat(skipNetworkCheck: true);
      final pending = await _store.unsynced();
      for (final capture in pending) {
        attempted++;
        await _store.markState(capture.id, 'SYNCING');
        final result = await _pushOne(capture);
        if (result.ok) {
          await _store.markSynced(capture.id);
          pushed++;
          continue;
        }
        final retry = SyncRetryPolicy.decide(
          previousRetries: capture.syncRetries,
          now: DateTime.now(),
        );
        await _store.recordRetry(
          id: capture.id,
          retries: retry.retryCount,
          error: result.error ?? 'upload_failed',
          nextRetryAt: retry.nextRetryAt,
          deadLetter: retry.deadLetter,
        );
        if (retry.deadLetter) {
          deadLettered++;
        } else if (nextRetry == null ||
            retry.nextRetryAt!.isBefore(nextRetry)) {
          nextRetry = retry.nextRetryAt;
        }
      }
      final pulled = await _pullAll();
      return SyncOutcome(
        online: true,
        pushed: pushed,
        pulled: pulled,
        attempted: attempted,
        deadLettered: deadLettered,
        nextRetryAt: nextRetry,
      );
    } on TimeoutException {
      return SyncOutcome(
        online: false,
        pushed: pushed,
        attempted: attempted,
        error: 'timeout',
      );
    } catch (error) {
      return SyncOutcome(
        online: false,
        pushed: pushed,
        attempted: attempted,
        error: error.toString(),
      );
    } finally {
      _busy = false;
    }
  }

  Future<_PushResult> _pushOne(Capture capture) async {
    try {
      final response = await http
          .post(
            Uri.parse(AppConfig.capturesEndpoint),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'capture_id': capture.id,
              'lat': capture.lat,
              'lon': capture.lon,
              'kind': capture.serverKind,
              'label': capture.type.label,
              'signals': {
                'accuracy_m': capture.accuracyM,
                'source': 'mobile_field',
                'neighborhood': capture.neighborhood,
                'speed': capture.speedMs,
                'course_deg': capture.courseDeg,
                'sensors': capture.sensorData,
              },
            }),
          )
          .timeout(AppConfig.httpTimeout);
      if (response.statusCode == 200 || response.statusCode == 201) {
        final decoded = jsonDecode(response.body);
        if (decoded is Map) {
          final neighborhood = decoded['neighborhood'] as String? ??
              ((decoded['metadata'] as Map?)?['neighborhood'] as String?);
          await _store.updateNeighborhood(capture.id, neighborhood);
        }
        return const _PushResult(true);
      }
      return _PushResult(
          false, 'http_${response.statusCode}: ${response.body}');
    } on TimeoutException {
      return const _PushResult(false, 'timeout');
    } catch (error) {
      return _PushResult(false, error.toString());
    }
  }

  Future<int> _pullAll() async {
    final response = await http
        .get(Uri.parse(AppConfig.capturesEndpoint))
        .timeout(AppConfig.httpTimeout);
    if (response.statusCode != 200) {
      throw StateError('pull_http_${response.statusCode}');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! List) throw const FormatException('captures_not_a_list');

    final local = await _store.loadCaptures();
    final mineIds = local
        .where((capture) => capture.owner == 1)
        .map((capture) => capture.id)
        .toSet();
    int pulled = 0;
    for (final item in decoded) {
      if (item is! Map) continue;
      final remote = Capture.fromServer(Map<String, dynamic>.from(item));
      if (mineIds.contains(remote.id)) continue;
      await _store.upsertRemote(remote);
      pulled++;
    }
    return pulled;
  }

  Future<bool> sendHeartbeat({bool skipNetworkCheck = false}) async {
    if (_lat == null || _lon == null) return false;
    if (!skipNetworkCheck && !await _hasRealNetwork()) return false;
    _deviceId ??= await _store.getOrCreateDeviceId();
    try {
      final response = await http
          .post(
            Uri.parse(AppConfig.heartbeatEndpoint),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'device_id': _deviceId,
              'session_id': _sessionId,
              'name': 'Agent MapNet',
              'platform': 'android',
              'app_version': '1.0.0',
              'lat': _lat,
              'lon': _lon,
              'accuracy_m': _accuracyM,
              'sensors': _sensors,
            }),
          )
          .timeout(AppConfig.httpTimeout);
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
