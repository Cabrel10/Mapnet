// =============================================================================
// MAPNET MOBILE — Application Android terrain (Offline-First / DTN / Mesh)
// Flutter 3.24 • Android 10+ (API 29-34)
// Style : Dark Mode Tactique / High-Contrast Geospatial
//
// v2 (refonte terrain) :
//   - Onboarding permissions runtime (plus d'ADB manuel).
//   - GPS RÉEL : flux temps réel, centrage caméra, marqueur "MA POSITION".
//   - Capture à la position GPS réelle du téléphone (plus le centre de carte).
//   - Synchronisation BIDIRECTIONNELLE avec le VPS (push + pull autres agents).
//   - HUD précision réelle (m) + cercle d'incertitude autour de l'utilisateur.
// =============================================================================

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import 'database/local_store.dart';
import 'models/capture.dart';
import 'services/geo_utils.dart';
import 'services/gps_service.dart';
import 'services/sensor_service.dart';
import 'services/sync_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
  ));
  runApp(const MapNetApp());
}

class MapNetApp extends StatelessWidget {
  const MapNetApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MapNet Terrain',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0A0E14),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFF57C00),
          secondary: Color(0xFF00E5A0),
          surface: Color(0xFF121821),
        ),
        fontFamily: 'monospace',
      ),
      home: const FieldMapScreen(),
    );
  }
}

class FieldMapScreen extends StatefulWidget {
  const FieldMapScreen({super.key});

  @override
  State<FieldMapScreen> createState() => _FieldMapScreenState();
}

class _FieldMapScreenState extends State<FieldMapScreen> {
  final MapController _mapController = MapController();
  final LocalStore _store = LocalStore.instance;

  static const LatLng _fallback = LatLng(3.8480, 11.5021); // Yaoundé

  List<Capture> _captures = [];
  LatLng? _myPos; // position GPS réelle de l'appareil
  double _accuracyM = 0; // précision horizontale réelle (m)
  int _pendingSync = 0;
  String _netMode = 'HORS-LIGNE';
  bool _permGranted = false;
  bool _followMe = true; // la caméra suit l'utilisateur
  SensorSnapshot _sensors = SensorSnapshot(measuredAt: DateTime.now());
  SyncOutcome? _lastSync;

  StreamSubscription<Position>? _posSub;
  StreamSubscription<SensorSnapshot>? _sensorSub;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _posSub?.cancel();
    _sensorSub?.cancel();
    SensorService.instance.stop();
    SyncService.instance.stop();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    await _store.init();
    await _refresh();
    await SensorService.instance.start();
    _sensorSub ??= SensorService.instance.stream.listen((snapshot) {
      if (!mounted) return;
      setState(() => _sensors = snapshot);
      final position = _myPos;
      if (position != null) {
        SyncService.instance.updatePresence(
          lat: position.latitude,
          lon: position.longitude,
          accuracyM: _accuracyM,
          sensors: snapshot.toJson(),
        );
      }
    });

    // 1) Permissions runtime (onboarding).
    final res = await GpsService.instance.ensurePermissions();
    if (res == GpsPermissionResult.granted) {
      setState(() => _permGranted = true);
      _startGps();
      _startSync();
    } else {
      if (mounted) _showPermissionSheet(res);
    }
  }

  void _startGps() {
    _posSub?.cancel();
    _posSub = GpsService.instance.stream().listen((p) {
      final ll = LatLng(p.latitude, p.longitude);
      setState(() {
        _myPos = ll;
        _accuracyM = p.accuracy;
      });
      SyncService.instance.updatePresence(
        lat: p.latitude,
        lon: p.longitude,
        accuracyM: p.accuracy,
        sensors: _sensors.toJson(),
      );
      if (_followMe) {
        _mapController.move(ll, _mapController.camera.zoom);
      }
    });
    // Fix initial rapide.
    GpsService.instance.current().then((p) {
      final ll = LatLng(p.latitude, p.longitude);
      setState(() {
        _myPos = ll;
        _accuracyM = p.accuracy;
      });
      SyncService.instance.updatePresence(
        lat: p.latitude,
        lon: p.longitude,
        accuracyM: p.accuracy,
        sensors: _sensors.toJson(),
      );
      _mapController.move(ll, 16);
    }).catchError((_) {});
  }

  void _startSync() {
    SyncService.instance.start((outcome) async {
      await _refresh();
      if (!mounted) return;
      setState(() {
        _netMode = outcome.online ? 'EN LIGNE (VPS)' : 'HORS-LIGNE';
        _lastSync = outcome;
      });
      if (outcome.online && (outcome.pushed > 0 || outcome.pulled > 0)) {
        _toast(
            'Sync ↑${outcome.pushed} ↓${outcome.pulled} avec le serveur',
            const Color(0xFF00E5A0));
      }
    });
  }

  Future<void> _refresh() async {
    final list = await _store.loadCaptures();
    setState(() {
      _captures = list;
      _pendingSync = list.where((c) => c.syncState != 'SYNCED').length;
    });
  }

  Future<void> _capture(CaptureType type) async {
    if (!_permGranted || _myPos == null) {
      _toast('Position GPS indisponible — vérifiez les permissions',
          const Color(0xFFEF4444));
      return;
    }
    // CAPTURE À LA POSITION GPS RÉELLE (plus le centre de la carte).
    Position pos;
    try {
      pos = await GpsService.instance.current();
    } catch (_) {
      _toast('Fix GPS échoué, réessayez', const Color(0xFFEF4444));
      return;
    }
    final acc = pos.accuracy;
    // Trust score dérivé de la précision réelle : plus précis => plus fiable.
    final trust = (1.0 - (acc / 50.0)).clamp(0.2, 0.98);
    final c = Capture(
      id: 'cap_${DateTime.now().millisecondsSinceEpoch}',
      lat: pos.latitude,
      lon: pos.longitude,
      type: type,
      trustScore: trust,
      syncState: 'PENDING',
      createdAt: DateTime.now(),
      accuracyM: acc,
      owner: 1,
      speedMs: pos.speed.isFinite ? pos.speed : null,
      courseDeg: pos.heading.isFinite ? pos.heading : null,
      sensorData: _sensors.toJson(),
    );
    await _store.insertCapture(c);
    await _refresh();
    _toast(
        '${type.label} @ ±${acc.toStringAsFixed(1)} m — file de synchro',
        const Color(0xFF00E5A0));
    // Tente une synchro immédiate.
    SyncService.instance.syncOnce().then((o) {
      _refresh();
      if (mounted) {
        setState(() {
          _netMode = o.online ? 'EN LIGNE (VPS)' : 'HORS-LIGNE';
          _lastSync = o;
        });
      }
    });
  }

  void _recenter() {
    if (_myPos == null) return;
    setState(() => _followMe = true);
    _mapController.move(_myPos!, 16);
  }

  void _toast(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: const Color(0xFF121821),
      content: Text(msg, style: TextStyle(color: color)),
      duration: const Duration(seconds: 2),
    ));
  }

  Color _trustColor(double t) {
    if (t >= 0.6) return const Color(0xFF00E5A0);
    if (t >= 0.3) return const Color(0xFFF57C00);
    return const Color(0xFFEF4444);
  }

  @override
  Widget build(BuildContext context) {
    final center = _myPos ?? _fallback;
    return Scaffold(
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: center,
              initialZoom: 15.5,
              minZoom: 3,
              maxZoom: 18,
              // Dès que l'utilisateur bouge la carte à la main, on arrête de le suivre.
              onPositionChanged: (pos, hasGesture) {
                if (hasGesture && _followMe) {
                  setState(() => _followMe = false);
                }
              },
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.cabrel10.mapnet_mobile',
                tileProvider: NetworkTileProvider(),
              ),

              // Cercle d'incertitude autour de MA position (précision réelle).
              if (_myPos != null && _accuracyM > 0)
                CircleLayer(circles: [
                  CircleMarker(
                    point: _myPos!,
                    radius: _accuracyM,
                    useRadiusInMeter: true,
                    color: const Color(0xFF2196F3).withOpacity(0.15),
                    borderColor: const Color(0xFF2196F3).withOpacity(0.6),
                    borderStrokeWidth: 1.5,
                  ),
                ]),

              // Marqueurs des captures (les miennes + celles des autres agents).
              MarkerLayer(
                markers: _captures
                    .map((c) => Marker(
                          point: LatLng(c.lat, c.lon),
                          width: 34,
                          height: 34,
                          child: Icon(
                            c.type.icon,
                            color: _trustColor(c.trustScore),
                            size: c.owner == 1 ? 30 : 26,
                            shadows: c.owner == 0
                                ? const [Shadow(color: Colors.black, blurRadius: 3)]
                                : null,
                          ),
                        ))
                    .toList(),
              ),

              // Marqueur "MA POSITION" (bleu, distinct des captures).
              if (_myPos != null)
                MarkerLayer(markers: [
                  Marker(
                    point: _myPos!,
                    width: 26,
                    height: 26,
                    child: _MeDot(),
                  ),
                ]),
            ],
          ),

          _buildHud(),
          _buildSyncBadge(),
          if (_myPos != null) _buildNearbyButton(),
          if (!_followMe && _myPos != null) _buildRecenterButton(),
        ],
      ),
      floatingActionButton: _buildCaptureFabs(),
    );
  }

  Widget _buildHud() {
    final hdop = GpsService.hdopFromAccuracy(_accuracyM);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: const Color(0xFF121821).withOpacity(0.92),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF1F2A38)),
          ),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
            children: [
              _hudTile(
                  Icons.gps_fixed,
                  'GPS',
                  _myPos == null
                      ? '—'
                      : '±${_accuracyM.toStringAsFixed(1)} m',
                  _myPos == null
                      ? const Color(0xFFEF4444)
                      : (_accuracyM <= 15
                          ? const Color(0xFF00E5A0)
                          : const Color(0xFFF57C00))),
              _hudTile(Icons.satellite_alt, 'HDOP',
                  _myPos == null ? '—' : hdop.toStringAsFixed(1), Colors.white),
              _hudTile(
                  Icons.hub,
                  'RÉSEAU',
                  _netMode.startsWith('EN LIGNE') ? 'EN LIGNE' : 'HORS-LIGNE',
                  _netMode.startsWith('EN LIGNE')
                      ? const Color(0xFF00E5A0)
                      : const Color(0xFFF57C00)),
              _hudTile(
                  Icons.storage, 'PTS', '${_captures.length}', Colors.white),
              _hudTile(
                  Icons.sync_problem,
                  'ATTENTE',
                  '$_pendingSync',
                  _pendingSync == 0
                      ? const Color(0xFF00E5A0)
                      : const Color(0xFFEF4444)),
              _hudTile(Icons.explore, 'CAP',
                  _sensors.headingDeg?.toStringAsFixed(0) ?? '—', Colors.white),
              _hudTile(Icons.speed, 'IMU', _sensors.hasImu ? 'RÉEL' : '—',
                  _sensors.hasImu ? const Color(0xFF00E5A0) : Colors.grey),
              _hudTile(Icons.directions_walk, 'PAS',
                  _sensors.steps?.toString() ?? '—', Colors.white),
            ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _hudTile(IconData icon, String label, String value, Color color) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 18),
        const SizedBox(height: 3),
        Text(label,
            style: const TextStyle(
                color: Color(0xFF6B7A8D), fontSize: 9, letterSpacing: 1)),
        Text(value,
            style: TextStyle(
                color: color, fontSize: 12, fontWeight: FontWeight.bold)),
      ],
    );
  }

  Widget _buildRecenterButton() {
    return Positioned(
      right: 16,
      bottom: 210,
      child: FloatingActionButton.small(
        heroTag: 'recenter',
        backgroundColor: const Color(0xFF1F2A38),
        onPressed: _recenter,
        child: const Icon(Icons.my_location, color: Color(0xFF2196F3)),
      ),
    );
  }

  /// Bouton "lieux à proximité" (navigation terrain).
  Widget _buildNearbyButton() {
    return Positioned(
      right: 16,
      bottom: 270,
      child: FloatingActionButton.small(
        heroTag: 'nearby',
        backgroundColor: const Color(0xFF1F2A38),
        onPressed: _showNearby,
        child: const Icon(Icons.explore, color: Color(0xFF00E5A0)),
      ),
    );
  }

  /// Liste des captures triées par distance depuis MA position (proximité).
  void _showNearby() {
    if (_myPos == null) {
      _toast('Position inconnue', const Color(0xFFEF4444));
      return;
    }
    final me = _myPos!;
    final ranked = _captures
        .map((c) => (
              cap: c,
              dist: GeoUtils.distanceMeters(me, LatLng(c.lat, c.lon)),
              brg: GeoUtils.bearingDeg(me, LatLng(c.lat, c.lon)),
            ))
        .toList()
      ..sort((a, b) => a.dist.compareTo(b.dist));

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF121821),
      showDragHandle: true,
      builder: (ctx) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.5,
        maxChildSize: 0.85,
        builder: (_, scroll) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 4, 20, 8),
              child: Text('LIEUX À PROXIMITÉ',
                  style: TextStyle(
                      color: Color(0xFF00E5A0),
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.5)),
            ),
            Expanded(
              child: ListView.builder(
                controller: scroll,
                itemCount: ranked.length,
                itemBuilder: (_, i) {
                  final r = ranked[i];
                  return ListTile(
                    leading: Icon(r.cap.type.icon,
                        color: _trustColor(r.cap.trustScore)),
                    title: Text(r.cap.type.label,
                        style: const TextStyle(color: Colors.white)),
                    subtitle: Text(
                      '${GeoUtils.humanDistance(r.dist)} · ${GeoUtils.compass(r.brg)} · '
                      '${r.cap.neighborhood ?? "quartier inconnu"} · '
                      '${r.cap.owner == 1 ? "à moi" : "autre agent"}',
                      style: const TextStyle(color: Color(0xFF9FB0C3)),
                    ),
                    trailing: const Icon(Icons.navigation,
                        color: Color(0xFFF57C00), size: 18),
                    onTap: () {
                      Navigator.pop(ctx);
                      setState(() => _followMe = false);
                      _mapController.move(LatLng(r.cap.lat, r.cap.lon), 17);
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSyncBadge() {
    final syncing = _pendingSync > 0;
    return Positioned(
      left: 12,
      bottom: 20,
      child: GestureDetector(
        onTap: _showSyncDetails,
        child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: const Color(0xFF121821).withOpacity(0.92),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: syncing
                  ? const Color(0xFFF57C00)
                  : const Color(0xFF00E5A0)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(syncing ? Icons.cloud_upload : Icons.cloud_done,
                size: 16,
                color: syncing
                    ? const Color(0xFFF57C00)
                    : const Color(0xFF00E5A0)),
            const SizedBox(width: 6),
            Text(
              syncing ? '$_pendingSync EN TRANSIT' : 'SYNCHRONISÉ',
              style: TextStyle(
                  color: syncing
                      ? const Color(0xFFF57C00)
                      : const Color(0xFF00E5A0),
                  fontSize: 11,
                  fontWeight: FontWeight.bold),
            ),
          ],
        ),
        ),
      ),
    );
  }

  Future<void> _showSyncDetails() async {
    final history = await _store.syncHistory(limit: 30);
    if (!mounted) return;
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF121821),
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              const Text('HISTORIQUE DE SYNCHRONISATION',
                  style: TextStyle(color: Color(0xFF00E5A0), fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text(
                'Tentées ${_lastSync?.attempted ?? 0} · envoyées ${_lastSync?.pushed ?? 0} · '
                'dead-letter ${_lastSync?.deadLettered ?? 0} · '
                'prochain retry ${_lastSync?.nextRetryAt?.toLocal().toIso8601String() ?? "—"}',
                style: const TextStyle(color: Color(0xFF9FB0C3), fontSize: 12),
              ),
              if (_lastSync?.error != null)
                Text(_lastSync!.error!, style: const TextStyle(color: Color(0xFFEF4444))),
              const Divider(),
              Expanded(
                child: ListView(
                  children: history
                      .map((row) => ListTile(
                            dense: true,
                            title: Text(row['message'] as String,
                                style: const TextStyle(color: Colors.white, fontSize: 12)),
                            subtitle: Text(row['ts'] as String,
                                style: const TextStyle(color: Color(0xFF6B7A8D), fontSize: 10)),
                          ))
                      .toList(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCaptureFabs() {
    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        FloatingActionButton.small(
          heroTag: 'pothole',
          backgroundColor: const Color(0xFF1F2A38),
          onPressed: () => _capture(CaptureType.roadDamage),
          child: const Icon(Icons.warning_amber, color: Color(0xFFEF4444)),
        ),
        const SizedBox(height: 10),
        FloatingActionButton.small(
          heroTag: 'voice',
          backgroundColor: const Color(0xFF1F2A38),
          onPressed: () => _capture(CaptureType.voiceNote),
          child: const Icon(Icons.mic, color: Color(0xFF00E5A0)),
        ),
        const SizedBox(height: 10),
        FloatingActionButton(
          heroTag: 'poi',
          backgroundColor: const Color(0xFFF57C00),
          onPressed: () => _capture(CaptureType.poi),
          child: const Icon(Icons.add_location_alt, color: Colors.white),
        ),
      ],
    );
  }

  // --- Onboarding permissions (modale) ---
  void _showPermissionSheet(GpsPermissionResult res) {
    final msg = switch (res) {
      GpsPermissionResult.serviceDisabled =>
        'La localisation de l\'appareil est désactivée. Activez le GPS pour cartographier le terrain.',
      GpsPermissionResult.deniedForever =>
        'Permission refusée définitivement. Ouvrez les réglages pour autoriser la localisation.',
      _ =>
        'MapNet a besoin de votre position pour vous situer sur la carte, capturer des points géoréférencés et vous guider vers les lieux à proximité.',
    };
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF121821),
      isDismissible: false,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.location_on, color: Color(0xFFF57C00), size: 40),
            const SizedBox(height: 12),
            const Text('Autorisation de localisation',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Text(msg, style: const TextStyle(color: Color(0xFF9FB0C3))),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFFF57C00)),
                onPressed: () async {
                  Navigator.pop(ctx);
                  if (res == GpsPermissionResult.deniedForever) {
                    await GpsService.instance.openSettings();
                  } else {
                    await _bootstrap();
                  }
                },
                child: Text(
                    res == GpsPermissionResult.deniedForever
                        ? 'OUVRIR LES RÉGLAGES'
                        : 'AUTORISER',
                    style: const TextStyle(
                        color: Colors.black, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Point bleu animé "MA POSITION" (halo pulsant).
class _MeDot extends StatefulWidget {
  @override
  State<_MeDot> createState() => _MeDotState();
}

class _MeDotState extends State<_MeDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
      vsync: this, duration: const Duration(seconds: 2))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (_, __) {
        final t = _c.value;
        return Stack(
          alignment: Alignment.center,
          children: [
            Container(
              width: 10 + 16 * t,
              height: 10 + 16 * t,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF2196F3).withOpacity((1 - t) * 0.4),
              ),
            ),
            Container(
              width: 14,
              height: 14,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF2196F3),
                border: Border.all(color: Colors.white, width: 2),
              ),
            ),
          ],
        );
      },
    );
  }
}
