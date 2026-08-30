import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mapnet_mobile_client/database/db_helper.dart';
import 'package:mapnet_mobile_client/main.dart';
import 'package:mapnet_mobile_client/sync/sync_manager.dart';

void main() {
  const summary = LocalDataSummary(
    localVersion: 12,
    serverVersion: 14,
    lastSyncAt: null,
    roadCount: 238,
    pendingTelemetryCount: 7,
  );

  testWidgets('affiche le statut local et synchronise', (tester) async {
    var syncCalls = 0;
    await tester.pumpWidget(
      MapNetDataMuleApp(
        summaryLoader: () async => summary,
        connectionChecker: () async => true,
        syncRunner: () async {
          syncCalls++;
          return SyncResult(
            success: true,
            localVersion: 14,
            serverVersion: 14,
            appliedChanges: 2,
            completedAt: DateTime(2026, 8, 30),
          );
        },
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('MapNet Data Mule'), findsOneWidget);
    expect(find.text('En ligne — synchronisation disponible'), findsOneWidget);
    expect(find.text('v12'), findsOneWidget);
    expect(find.text('238'), findsOneWidget);
    expect(find.text('7'), findsOneWidget);

    await tester.drag(find.byType(ListView), const Offset(0, -500));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('syncButton')));
    await tester.pumpAndSettle();

    expect(syncCalls, 1);
    expect(find.text('2 modification(s) appliquée(s)'), findsOneWidget);
  });

  testWidgets('rend le mode hors-ligne explicitement', (tester) async {
    await tester.pumpWidget(
      MapNetDataMuleApp(
        summaryLoader: () async => summary,
        connectionChecker: () async => false,
        syncRunner: () async => SyncResult(
          success: false,
          localVersion: 12,
          serverVersion: 0,
          appliedChanges: 0,
          completedAt: DateTime(2026, 8, 30),
          error: 'réseau indisponible',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Hors ligne — données locales actives'), findsOneWidget);
  });
}
