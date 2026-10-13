import 'package:flutter_test/flutter_test.dart';
import 'package:mapnet_mobile/config/app_config.dart';
import 'package:mapnet_mobile/services/sync_retry_policy.dart';

void main() {
  group('SyncRetryPolicy', () {
    final now = DateTime.utc(2026, 8, 2, 12);

    test('applique un backoff exponentiel persistant', () {
      final expectedSeconds = <int>[60, 120, 240, 480];
      for (var previousRetries = 0;
          previousRetries < expectedSeconds.length;
          previousRetries++) {
        final decision = SyncRetryPolicy.decide(
          previousRetries: previousRetries,
          now: now,
        );
        final expectedDelay =
            Duration(seconds: expectedSeconds[previousRetries]);

        expect(decision.retryCount, previousRetries + 1);
        expect(decision.deadLetter, isFalse);
        expect(decision.delay, expectedDelay);
        expect(decision.nextRetryAt, now.add(expectedDelay));
      }
    });

    test('place la cinquième tentative en dead-letter sans prochain retry', () {
      final decision = SyncRetryPolicy.decide(
        previousRetries: AppConfig.maxRetries - 1,
        now: now,
      );

      expect(decision.retryCount, AppConfig.maxRetries);
      expect(decision.deadLetter, isTrue);
      expect(decision.delay, isNull);
      expect(decision.nextRetryAt, isNull);
    });
  });
}
