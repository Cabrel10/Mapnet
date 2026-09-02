import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import 'mapnet_api.dart';
import 'navigation_math.dart';
import 'navigation_sensors.dart';

class NavigationScreen extends StatefulWidget {
  const NavigationScreen({
    super.key,
    required this.gatewayUrl,
    this.api,
    this.sensorController,
  });

  final String gatewayUrl;
  final MapNetApi? api;
  final NavigationSensorController? sensorController;

  @override
  State<NavigationScreen> createState() => _NavigationScreenState();
}

class _NavigationScreenState extends State<NavigationScreen> {
  static const LatLng _yaounde = LatLng(3.8480, 11.5021);

  final MapController _mapController = MapController();
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  late final MapNetApi _api;
  late final NavigationSensorController _sensorController;
  late final bool _ownsSensorController;
  StreamSubscription<Position>? _positionSubscription;
  StreamSubscription<NavigationSensorState>? _sensorSubscription;
  Timer? _searchDebounce;
  LatLng? _position;
  double _accuracyM = 0;
  NavigationSensorState _sensorState = const NavigationSensorState();
  DateTime? _offRouteSince;
  DateTime? _lastRerouteAt;
  double? _routeDistanceM;
  PlaceResult? _destination;
  NavigationRoute? _route;
  List<PlaceResult> _results = const [];
  bool _searching = false;
  bool _routing = false;
  bool _navigating = false;
  int _stepIndex = 0;
  String? _message;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? MapNetApi(gatewayUrl: widget.gatewayUrl);
    _ownsSensorController = widget.sensorController == null;
    _sensorController = widget.sensorController ?? NavigationSensorController();
    _sensorSubscription = _sensorController.stream.listen((state) {
      if (mounted) setState(() => _sensorState = state);
    });
    _sensorController.start();
    _startLocation();
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _positionSubscription?.cancel();
    _sensorSubscription?.cancel();
    if (_ownsSensorController) _sensorController.dispose();
    _searchController.dispose();
    _searchFocus.dispose();
    if (widget.api == null) _api.close();
    super.dispose();
  }

  Future<void> _startLocation() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        setState(
            () => _message = 'Activez le GPS pour démarrer un itinéraire.');
        return;
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        setState(
            () => _message = 'Autorisez la localisation pour vous guider.');
        return;
      }
      final first = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 15),
      );
      _updatePosition(first, recenter: true);
      _positionSubscription = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 8,
        ),
      ).listen(_updatePosition);
    } catch (error) {
      if (mounted) {
        setState(() => _message = 'Position indisponible : $error');
      }
    }
  }

  void _updatePosition(Position position, {bool recenter = false}) {
    if (!mounted) return;
    final point = LatLng(position.latitude, position.longitude);
    setState(() {
      _position = point;
      _accuracyM = position.accuracy;
    });
    if (_navigating) {
      _advanceStep(point);
      _evaluateReroute(point);
    }
    if (recenter || _navigating) {
      _mapController.move(point, _navigating ? 17 : 15.5);
    }
  }

  void _advanceStep(LatLng point) {
    final route = _route;
    if (route == null || route.steps.isEmpty) return;
    const distance = Distance();
    var nextIndex = _stepIndex;
    while (nextIndex < route.steps.length - 1 &&
        distance.as(
              LengthUnit.Meter,
              point,
              route.steps[nextIndex].position,
            ) <
            40) {
      nextIndex++;
    }
    if (nextIndex != _stepIndex && mounted) {
      setState(() => _stepIndex = nextIndex);
    }
  }

  void _evaluateReroute(LatLng point) {
    final route = _route;
    final destination = _destination;
    if (route == null || destination == null || route.points.isEmpty) return;

    final proximity = NavigationMath.closestRouteSegment(point, route.points);
    final decision = NavigationMath.shouldReroute(
      distanceM: proximity.distanceM,
      accuracyM: _accuracyM,
      now: DateTime.now(),
      offRouteSince: _offRouteSince,
      lastRerouteAt: _lastRerouteAt,
      rerouting: _routing,
    );
    if (mounted) {
      setState(() {
        _routeDistanceM = proximity.distanceM;
        _offRouteSince = decision.offRouteSince;
      });
    }
    if (decision.trigger) {
      _rerouteFrom(point, destination.position);
    }
  }

  Future<void> _rerouteFrom(LatLng origin, LatLng destination) async {
    if (_routing) return;
    final startedAt = DateTime.now();
    setState(() {
      _routing = true;
      _lastRerouteAt = startedAt;
      _offRouteSince = null;
      _message = 'Déviation confirmée, recalcul de l’itinéraire…';
    });
    try {
      final route = await _api.navigate(from: origin, to: destination);
      if (!mounted || _destination?.position != destination) return;
      setState(() {
        _route = route;
        _routing = false;
        _stepIndex = 0;
        _routeDistanceM = 0;
        _message = 'Nouvel itinéraire prêt.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _routing = false;
        _message = 'Recalcul impossible : $error';
      });
    }
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    final query = value.trim();
    if (query.length < 2) {
      setState(() {
        _results = const [];
        _searching = false;
      });
      return;
    }
    _searchDebounce = Timer(const Duration(milliseconds: 350), () {
      _search(query);
    });
  }

  Future<void> _search(String query) async {
    setState(() {
      _searching = true;
      _message = null;
    });
    try {
      final results = await _api.search(query, near: _position);
      if (!mounted || _searchController.text.trim() != query) return;
      setState(() {
        _results = results;
        _searching = false;
        if (results.isEmpty) _message = 'Aucun lieu trouvé au Cameroun.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _results = const [];
        _searching = false;
        _message = error.toString();
      });
    }
  }

  Future<void> _selectDestination(PlaceResult place) async {
    _searchFocus.unfocus();
    _searchController.text = place.name;
    setState(() {
      _destination = place;
      _results = const [];
    });
    await _calculateRoute(place.position);
  }

  Future<void> _selectMapDestination(LatLng point) async {
    final place = PlaceResult(
      id: 'map-selection',
      name: 'Destination choisie',
      kind: 'map',
      city: '',
      position: point,
    );
    setState(() {
      _destination = place;
      _searchController.text = place.name;
      _results = const [];
    });
    await _calculateRoute(point);
  }

  Future<void> _calculateRoute(LatLng destination) async {
    final origin = _position;
    if (origin == null) {
      setState(
          () => _message = 'Position GPS requise pour calculer le trajet.');
      return;
    }
    setState(() {
      _routing = true;
      _navigating = false;
      _route = null;
      _stepIndex = 0;
      _offRouteSince = null;
      _routeDistanceM = null;
      _message = null;
    });
    try {
      final route = await _api.navigate(from: origin, to: destination);
      if (!mounted) return;
      setState(() {
        _route = route;
        _routing = false;
        _offRouteSince = null;
        _routeDistanceM = 0;
      });
      _mapController.fitCamera(
        CameraFit.bounds(
          bounds: LatLngBounds.fromPoints(route.points),
          padding: const EdgeInsets.fromLTRB(44, 150, 44, 220),
        ),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _routing = false;
        _message = error.toString();
      });
    }
  }

  void _clearRoute() {
    setState(() {
      _destination = null;
      _route = null;
      _navigating = false;
      _stepIndex = 0;
      _offRouteSince = null;
      _lastRerouteAt = null;
      _routeDistanceM = null;
      _searchController.clear();
      _message = null;
    });
  }

  void _toggleNavigation() {
    if (_route == null) return;
    setState(() {
      _navigating = !_navigating;
      _stepIndex = 0;
      _offRouteSince = null;
      _routeDistanceM = null;
    });
    if (_navigating && _position != null) {
      _mapController.move(_position!, 17);
    }
  }

  String _placeSubtitle(PlaceResult place) {
    final parts = <String>[
      if (place.category?.isNotEmpty == true) place.category!,
      if (place.city.isNotEmpty) place.city,
      if (place.distanceM != null)
        place.distanceM! >= 1000
            ? '${(place.distanceM! / 1000).toStringAsFixed(1)} km'
            : '${place.distanceM!.round()} m',
    ];
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final route = _route;
    final currentStep = route != null &&
            route.steps.isNotEmpty &&
            _stepIndex < route.steps.length
        ? route.steps[_stepIndex]
        : null;
    return Scaffold(
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: _yaounde,
              initialZoom: 13,
              minZoom: 3,
              maxZoom: 19,
              onLongPress: (_, point) => _selectMapDestination(point),
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.cabrel10.mapnet_mobile_client',
              ),
              if (route != null)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: route.points,
                      strokeWidth: 8,
                      color: Colors.white.withOpacity(0.85),
                    ),
                    Polyline(
                      points: route.points,
                      strokeWidth: 5,
                      color: const Color(0xFF1677FF),
                    ),
                  ],
                ),
              if (_position != null && _accuracyM > 0)
                CircleLayer(
                  circles: [
                    CircleMarker(
                      point: _position!,
                      radius: _accuracyM,
                      useRadiusInMeter: true,
                      color: const Color(0xFF1677FF).withOpacity(0.12),
                      borderColor: const Color(0xFF1677FF).withOpacity(0.35),
                      borderStrokeWidth: 1,
                    ),
                  ],
                ),
              MarkerLayer(
                markers: [
                  if (_position != null)
                    Marker(
                      point: _position!,
                      width: 28,
                      height: 28,
                      child: Transform.rotate(
                        angle: NavigationMath.normalizeHeading(
                              _sensorState.headingDeg ?? 0,
                            ) *
                            math.pi /
                            180,
                        child: Container(
                          decoration: BoxDecoration(
                            color: const Color(0xFF1677FF),
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 3),
                            boxShadow: const [
                              BoxShadow(color: Colors.black26, blurRadius: 5),
                            ],
                          ),
                          child: const Icon(
                            Icons.navigation,
                            color: Colors.white,
                            size: 17,
                          ),
                        ),
                      ),
                    ),
                  if (_destination != null)
                    Marker(
                      point: _destination!.position,
                      width: 44,
                      height: 44,
                      child: const Icon(
                        Icons.location_pin,
                        color: Color(0xFFE53935),
                        size: 44,
                      ),
                    ),
                ],
              ),
            ],
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Material(
                    elevation: 5,
                    borderRadius: BorderRadius.circular(18),
                    child: TextField(
                      key: const Key('destinationSearch'),
                      controller: _searchController,
                      focusNode: _searchFocus,
                      onChanged: _onSearchChanged,
                      textInputAction: TextInputAction.search,
                      decoration: InputDecoration(
                        hintText: 'Où allez-vous ?',
                        prefixIcon: const Icon(Icons.search),
                        suffixIcon: _searching
                            ? const Padding(
                                padding: EdgeInsets.all(14),
                                child: SizedBox.square(
                                  dimension: 18,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                ),
                              )
                            : (_destination != null
                                ? IconButton(
                                    onPressed: _clearRoute,
                                    icon: const Icon(Icons.close),
                                  )
                                : null),
                        filled: true,
                        fillColor: Theme.of(context).colorScheme.surface,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(18),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ),
                  if (_results.isNotEmpty)
                    Material(
                      elevation: 5,
                      borderRadius: const BorderRadius.vertical(
                        bottom: Radius.circular(16),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxHeight: 330),
                        child: ListView.separated(
                          padding: EdgeInsets.zero,
                          shrinkWrap: true,
                          itemCount: _results.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (_, index) {
                            final place = _results[index];
                            return ListTile(
                              leading: const CircleAvatar(
                                child: Icon(Icons.place_outlined),
                              ),
                              title: Text(place.name),
                              subtitle: Text(_placeSubtitle(place)),
                              onTap: () => _selectDestination(place),
                            );
                          },
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
          Positioned(
            top: 88,
            left: 16,
            right: 16,
            child: SafeArea(
              child: Align(
                alignment: Alignment.centerRight,
                child: Material(
                  elevation: 3,
                  borderRadius: BorderRadius.circular(12),
                  color:
                      Theme.of(context).colorScheme.surface.withOpacity(0.94),
                  child: Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    child: Wrap(
                      spacing: 12,
                      runSpacing: 4,
                      children: [
                        Text('GPS ±${_accuracyM.toStringAsFixed(0)} m'),
                        Text(_sensorState.headingDeg == null
                            ? 'CAP —'
                            : 'CAP ${_sensorState.headingDeg!.round()}°'),
                        Text(_sensorState.hasAccelerometer &&
                                _sensorState.hasGyroscope
                            ? 'IMU actif'
                            : 'IMU —'),
                        if (_navigating && _routeDistanceM != null)
                          Text('Trace ${_routeDistanceM!.round()} m'),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          if (_message != null)
            Positioned(
              top: 138,
              left: 16,
              right: 16,
              child: SafeArea(
                child: Material(
                  color: Theme.of(context).colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(12),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        const Icon(Icons.info_outline),
                        const SizedBox(width: 8),
                        Expanded(child: Text(_message!)),
                        IconButton(
                          onPressed: () => setState(() => _message = null),
                          icon: const Icon(Icons.close),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          Positioned(
            right: 16,
            bottom: route == null ? 28 : 202,
            child: FloatingActionButton.small(
              heroTag: 'client-recenter',
              onPressed: _position == null
                  ? _startLocation
                  : () => _mapController.move(_position!, 16),
              child: const Icon(Icons.my_location),
            ),
          ),
          if (_routing)
            const Positioned.fill(
              child: IgnorePointer(
                child: Center(child: CircularProgressIndicator()),
              ),
            ),
          if (route != null)
            Positioned(
              left: 12,
              right: 12,
              bottom: 12,
              child: SafeArea(
                top: false,
                child: Card(
                  elevation: 8,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _navigating
                              ? (currentStep?.instruction ?? 'Continuez')
                              : (_destination?.name ?? 'Itinéraire'),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style:
                              Theme.of(context).textTheme.titleMedium?.copyWith(
                                    fontWeight: FontWeight.bold,
                                  ),
                        ),
                        const SizedBox(height: 6),
                        Text('${route.durationLabel} · ${route.distanceLabel}'),
                        if (_navigating && route.steps.isNotEmpty)
                          Text(
                            'Étape ${_stepIndex + 1}/${route.steps.length}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: FilledButton.icon(
                                key: const Key('startNavigation'),
                                onPressed: _toggleNavigation,
                                icon: Icon(
                                  _navigating ? Icons.stop : Icons.navigation,
                                ),
                                label: Text(
                                  _navigating ? 'Arrêter' : 'Démarrer',
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton.filledTonal(
                              tooltip: 'Effacer l’itinéraire',
                              onPressed: _clearRoute,
                              icon: const Icon(Icons.close),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
