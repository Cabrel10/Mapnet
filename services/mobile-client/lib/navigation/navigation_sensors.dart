import 'dart:async';
import 'dart:math' as math;

import 'package:flutter_compass/flutter_compass.dart';
import 'package:sensors_plus/sensors_plus.dart';

class NavigationSensorState {
  const NavigationSensorState({
    this.headingDeg,
    this.accelerationMs2,
    this.rotationRadS,
  });

  final double? headingDeg;
  final double? accelerationMs2;
  final double? rotationRadS;

  bool get hasCompass => headingDeg != null;
  bool get hasAccelerometer => accelerationMs2 != null;
  bool get hasGyroscope => rotationRadS != null;

  NavigationSensorState copyWith({
    double? headingDeg,
    double? accelerationMs2,
    double? rotationRadS,
  }) {
    return NavigationSensorState(
      headingDeg: headingDeg ?? this.headingDeg,
      accelerationMs2: accelerationMs2 ?? this.accelerationMs2,
      rotationRadS: rotationRadS ?? this.rotationRadS,
    );
  }
}

class NavigationSensorController {
  final _controller = StreamController<NavigationSensorState>.broadcast();
  StreamSubscription<CompassEvent>? _compassSubscription;
  StreamSubscription<AccelerometerEvent>? _accelerometerSubscription;
  StreamSubscription<GyroscopeEvent>? _gyroscopeSubscription;
  NavigationSensorState _state = const NavigationSensorState();

  Stream<NavigationSensorState> get stream => _controller.stream;
  NavigationSensorState get current => _state;

  void start() {
    if (_compassSubscription != null ||
        _accelerometerSubscription != null ||
        _gyroscopeSubscription != null) {
      return;
    }
    final compass = FlutterCompass.events;
    if (compass != null) {
      _compassSubscription = compass.listen(
        (event) {
          final heading = event.heading;
          if (heading != null && heading.isFinite) {
            _publish(_state.copyWith(headingDeg: (heading % 360 + 360) % 360));
          }
        },
        onError: (_) {},
      );
    }
    _accelerometerSubscription = accelerometerEventStream(
      samplingPeriod: SensorInterval.uiInterval,
    ).listen(
      (event) => _publish(
        _state.copyWith(
          accelerationMs2: math.sqrt(
            event.x * event.x + event.y * event.y + event.z * event.z,
          ),
        ),
      ),
      onError: (_) {},
    );
    _gyroscopeSubscription = gyroscopeEventStream(
      samplingPeriod: SensorInterval.uiInterval,
    ).listen(
      (event) => _publish(
        _state.copyWith(
          rotationRadS: math.sqrt(
            event.x * event.x + event.y * event.y + event.z * event.z,
          ),
        ),
      ),
      onError: (_) {},
    );
  }

  void _publish(NavigationSensorState value) {
    _state = value;
    if (!_controller.isClosed) _controller.add(value);
  }

  Future<void> dispose() async {
    await _compassSubscription?.cancel();
    await _accelerometerSubscription?.cancel();
    await _gyroscopeSubscription?.cancel();
    await _controller.close();
  }
}
