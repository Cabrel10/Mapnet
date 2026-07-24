// =============================================================================
// MAPNET MOBILE — Application Android terrain (Offline-First / DTN / Mesh)
// Flutter 3.24 • Android 10+ (API 29-34)
// Style : Dark Mode Tactique / High-Contrast Geospatial
// =============================================================================

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import 'database/local_store.dart';
import 'models/capture.dart';

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

  // Point de départ : Ouagadougou (cohérent avec le seed du serveur DDD).
  static const LatLng _origin = LatLng(12.3714, -1.5197);

  List<Capture> _captures = [];
  double _gpsAccuracy = 4.2; // mètres (HDOP simulée en preview)
  int _pendingSync = 0;
  String _netMode = 'MESH P2P'; // ONLINE / MESH P2P / DTN LOCAL

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _store.init();
    final existing = await _store.loadCaptures();
    if (existing.isEmpty) {
      await _store.seedDemo(_origin);
    }
    await _refresh();
  }

  Future<void> _refresh() async {
    final list = await _store.loadCaptures();
    setState(() {
      _captures = list;
      _pendingSync = list.where((c) => c.syncState != 'SYNCED').length;
    });
  }

  Future<void> _capture(CaptureType type) async {
    // Capture 1-tap au centre de la carte (offline, écrit dans SQLite local).
    final center = _mapController.camera.center;
    final c = Capture(
      id: 'cap_${DateTime.now().millisecondsSinceEpoch}',
      lat: center.latitude,
      lon: center.longitude,
      type: type,
      trustScore: 0.55 + (type == CaptureType.poi ? 0.30 : 0.10),
      syncState: 'PENDING',
      createdAt: DateTime.now(),
    );
    await _store.insertCapture(c);
    await _refresh();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: const Color(0xFF121821),
        content: Text('Capture ${type.label} enregistrée localement (SQLite)',
            style: const TextStyle(color: Color(0xFF00E5A0))),
        duration: const Duration(seconds: 2),
      ));
    }
  }

  Color _trustColor(double t) {
    if (t >= 0.6) return const Color(0xFF00E5A0);
    if (t >= 0.3) return const Color(0xFFF57C00);
    return const Color(0xFFEF4444);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          // -- Carte offline-first (tuiles OSM raster, cache local) --
          FlutterMap(
            mapController: _mapController,
            options: const MapOptions(
              initialCenter: _origin,
              initialZoom: 13.5,
              minZoom: 3,
              maxZoom: 18,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.cabrel10.mapnet_mobile',
                tileProvider: NetworkTileProvider(),
              ),
              MarkerLayer(
                markers: _captures
                    .map((c) => Marker(
                          point: LatLng(c.lat, c.lon),
                          width: 34,
                          height: 34,
                          child: Icon(c.type.icon,
                              color: _trustColor(c.trustScore), size: 30),
                        ))
                    .toList(),
              ),
            ],
          ),

          // -- HUD de télémesure (en-tête) --
          _buildHud(),

          // -- Indicateur de synchronisation (bas) --
          _buildSyncBadge(),
        ],
      ),
      floatingActionButton: _buildCaptureFabs(),
    );
  }

  Widget _buildHud() {
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
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _hudTile(Icons.gps_fixed, 'GPS',
                  '${_gpsAccuracy.toStringAsFixed(1)} m', const Color(0xFF00E5A0)),
              _hudTile(Icons.hub, 'RÉSEAU', _netMode,
                  _netMode == 'ONLINE' ? const Color(0xFF00E5A0) : const Color(0xFFF57C00)),
              _hudTile(Icons.storage, 'LOCAL',
                  '${_captures.length} pts', Colors.white),
              _hudTile(Icons.sync_problem, 'ATTENTE',
                  '$_pendingSync', _pendingSync == 0 ? const Color(0xFF00E5A0) : const Color(0xFFEF4444)),
            ],
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

  Widget _buildSyncBadge() {
    final syncing = _pendingSync > 0;
    return Positioned(
      left: 12,
      bottom: 20,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: const Color(0xFF121821).withOpacity(0.92),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: syncing ? const Color(0xFFF57C00) : const Color(0xFF00E5A0)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(syncing ? Icons.cloud_upload : Icons.cloud_done,
                size: 16,
                color: syncing ? const Color(0xFFF57C00) : const Color(0xFF00E5A0)),
            const SizedBox(width: 6),
            Text(
              syncing ? 'TRANSIT MESH / DTN' : 'SYNCHRO SERVEUR',
              style: TextStyle(
                  color: syncing ? const Color(0xFFF57C00) : const Color(0xFF00E5A0),
                  fontSize: 11,
                  fontWeight: FontWeight.bold),
            ),
          ],
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
}
