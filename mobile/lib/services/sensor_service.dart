// MAPNET MOBILE — Flux de capteurs physiques. Aucune valeur simulée.
import 'dart:async';

import 'package:flutter_compass/flutter_compass.dart';
import 'package:pedometer/pedometer.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:sensors_plus/sensors_plus.dart';

class SensorSnapshot {
  final double? headingDeg;
  final double? accelX;
  final double? accelY;
  final double? accelZ;
  final double? gyroX;
  final double? gyroY;
  final double? gyroZ;
  final int? steps;
  final DateTime measuredAt;

  const SensorSnapshot({
    this.headingDeg,
    this.accelX,
    this.accelY,
    this.accelZ,
    this.gyroX,
    this.gyroY,
    this.gyroZ,
    this.steps,
    required this.measuredAt,
  });

  bool get hasCompass => headingDeg != null;
  bool get hasImu => accelX != null && gyroX != null;
  bool get hasPedometer => steps != null;

  Map<String, dynamic> toJson() => {
        'measured_at': measuredAt.toUtc().toIso8601String(),
        'heading_deg': headingDeg,
        'accelerometer_ms2': accelX == null
            ? null
            : {'x': accelX, 'y': accelY, 'z': accelZ},
        'gyroscope_rads': gyroX == null
            ? null
            : {'x': gyroX, 'y': gyroY, 'z': gyroZ},
        'steps': steps,
        'source': 'physical_sensors',
      };
}

class SensorService {
  SensorService._();
  static final SensorService instance = SensorService._();

  final _controller = StreamController<SensorSnapshot>.broadcast();
  final List<StreamSubscription<dynamic>> _subscriptions = [];
  SensorSnapshot _latest = SensorSnapshot(measuredAt: DateTime.now());
  bool _started = false;

  Stream<SensorSnapshot> get stream => _controller.stream;
  SensorSnapshot get latest => _latest;

  Future<void> start() async {
    if (_started) return;
    _started = true;
    await Permission.activityRecognition.request();

    final compass = FlutterCompass.events;
    if (compass != null) {
      _subscriptions.add(compass.listen(
        (event) => _publish(headingDeg: event.heading),
        onError: (_) {},
      ));
    }
    _subscriptions.add(accelerometerEventStream().listen(
      (event) => _publish(accel: event),
      onError: (_) {},
    ));
    _subscriptions.add(gyroscopeEventStream().listen(
      (event) => _publish(gyro: event),
      onError: (_) {},
    ));
    _subscriptions.add(Pedometer.stepCountStream.listen(
      (event) => _publish(steps: event.steps),
      onError: (_) {},
    ));
  }

  void _publish({
    double? headingDeg,
    AccelerometerEvent? accel,
    GyroscopeEvent? gyro,
    int? steps,
  }) {
    _latest = SensorSnapshot(
      headingDeg: headingDeg ?? _latest.headingDeg,
      accelX: accel?.x ?? _latest.accelX,
      accelY: accel?.y ?? _latest.accelY,
      accelZ: accel?.z ?? _latest.accelZ,
      gyroX: gyro?.x ?? _latest.gyroX,
      gyroY: gyro?.y ?? _latest.gyroY,
      gyroZ: gyro?.z ?? _latest.gyroZ,
      steps: steps ?? _latest.steps,
      measuredAt: DateTime.now(),
    );
    _controller.add(_latest);
  }

  Future<void> stop() async {
    for (final subscription in _subscriptions) {
      await subscription.cancel();
    }
    _subscriptions.clear();
    _started = false;
  }
}
