import 'dart:math';

import '../config/app_config.dart';

/// Décision pure et testable du cycle de retry persistant.
class SyncRetryDecision {
  final int retryCount;
  final bool deadLetter;
  final Duration? delay;
  final DateTime? nextRetryAt;

  const SyncRetryDecision({
    required this.retryCount,
    required this.deadLetter,
    required this.delay,
    required this.nextRetryAt,
  });
}

class SyncRetryPolicy {
  const SyncRetryPolicy._();

  static SyncRetryDecision decide({
    required int previousRetries,
    required DateTime now,
  }) {
    final retryCount = previousRetries + 1;
    final deadLetter = retryCount >= AppConfig.maxRetries;
    if (deadLetter) {
      return SyncRetryDecision(
        retryCount: retryCount,
        deadLetter: true,
        delay: null,
        nextRetryAt: null,
      );
    }

    final seconds = AppConfig.initialBackoffSeconds *
        pow(AppConfig.backoffMultiplier, retryCount - 1).toInt();
    final delay = Duration(seconds: seconds);
    return SyncRetryDecision(
      retryCount: retryCount,
      deadLetter: false,
      delay: delay,
      nextRetryAt: now.add(delay),
    );
  }
}
