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
  // Filtre passe-bas exponentiel (EMA). alpha petit = lissage fort.
  // Les gyro/accéléromètre bruts vibrent fortement en déplacement terrain ;
  // sans lissage le heading visuel et les magnitudes sont inexploitables.
  static const double _alpha = 0.15;
  // Correction d'offset gyroscope : biais moyen appris au repos pendant les
  // [_calibrationSamples] premières mesures (capteur immobile au démarrage).
  static const int _calibrationSamples = 40;
  // Seuil de repos gyro (rad/s) : au-dessus, on suspend la calibration.
  static const double _restThresholdRadS = 0.05;

  final _controller = StreamController<NavigationSensorState>.broadcast();
  StreamSubscription<CompassEvent>? _compassSubscription;
  StreamSubscription<AccelerometerEvent>? _accelerometerSubscription;
  StreamSubscription<GyroscopeEvent>? _gyroscopeSubscription;
  NavigationSensorState _state = const NavigationSensorState();

  double? _smoothAccel;
  double? _smoothGyro;
  double _gyroBias = 0;
  int _gyroCalibCount = 0;

  double _lowPass(double? previous, double next) =>
      previous == null ? next : previous + _alpha * (next - previous);

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
      (event) {
        final raw = math.sqrt(
          event.x * event.x + event.y * event.y + event.z * event.z,
        );
        _smoothAccel = _lowPass(_smoothAccel, raw);
        _publish(_state.copyWith(accelerationMs2: _smoothAccel));
      },
      onError: (_) {},
    );
    _gyroscopeSubscription = gyroscopeEventStream(
      samplingPeriod: SensorInterval.uiInterval,
    ).listen(
      (event) {
        final raw = math.sqrt(
          event.x * event.x + event.y * event.y + event.z * event.z,
        );
        // Calibration du biais au repos : tant que le capteur est quasi
        // immobile, on accumule la moyenne ; ensuite on la soustrait.
        if (_gyroCalibCount < _calibrationSamples && raw < _restThresholdRadS) {
          _gyroBias =
              (_gyroBias * _gyroCalibCount + raw) / (_gyroCalibCount + 1);
          _gyroCalibCount++;
        }
        final corrected = math.max(0.0, raw - _gyroBias);
        _smoothGyro = _lowPass(_smoothGyro, corrected);
        _publish(_state.copyWith(rotationRadS: _smoothGyro));
      },
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
