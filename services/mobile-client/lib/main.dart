import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

import 'database/db_helper.dart';
import 'sync/sync_manager.dart';

const String mapNetGateway = String.fromEnvironment(
  'MAPNET_GATEWAY',
  defaultValue: 'http://169.58.67.16:8080',
);

typedef SummaryLoader = Future<LocalDataSummary> Function();
typedef SyncRunner = Future<SyncResult> Function();
typedef ConnectionChecker = Future<bool> Function();

void main() {
  runApp(const MapNetDataMuleApp());
}

class MapNetDataMuleApp extends StatelessWidget {
  const MapNetDataMuleApp({
    super.key,
    this.summaryLoader,
    this.syncRunner,
    this.connectionChecker,
  });

  final SummaryLoader? summaryLoader;
  final SyncRunner? syncRunner;
  final ConnectionChecker? connectionChecker;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'MapNet Data Mule',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF075E54),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: DataMuleDashboard(
        summaryLoader: summaryLoader,
        syncRunner: syncRunner,
        connectionChecker: connectionChecker,
      ),
    );
  }
}

class DataMuleDashboard extends StatefulWidget {
  const DataMuleDashboard({
    super.key,
    this.summaryLoader,
    this.syncRunner,
    this.connectionChecker,
  });

  final SummaryLoader? summaryLoader;
  final SyncRunner? syncRunner;
  final ConnectionChecker? connectionChecker;

  @override
  State<DataMuleDashboard> createState() => _DataMuleDashboardState();
}

class _DataMuleDashboardState extends State<DataMuleDashboard> {
  LocalDataSummary? _summary;
  SyncResult? _lastResult;
  bool _isOnline = false;
  bool _isLoading = true;
  bool _isSyncing = false;
  String? _statusError;

  SummaryLoader get _summaryLoader =>
      widget.summaryLoader ?? DatabaseHelper.instance.getLocalSummary;

  Future<bool> _defaultConnectionChecker() async {
    final results = await Connectivity().checkConnectivity();
    return !results.contains(ConnectivityResult.none);
  }

  @override
  void initState() {
    super.initState();
    _refreshStatus();
  }

  Future<void> _refreshStatus() async {
    if (mounted) {
      setState(() {
        _isLoading = true;
        _statusError = null;
      });
    }
    try {
      final values = await Future.wait<Object>([
        _summaryLoader(),
        (widget.connectionChecker ?? _defaultConnectionChecker)(),
      ]);
      if (!mounted) return;
      setState(() {
        _summary = values[0] as LocalDataSummary;
        _isOnline = values[1] as bool;
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _statusError = 'Lecture locale impossible : $error';
        _isLoading = false;
      });
    }
  }

  Future<void> _synchronize() async {
    setState(() {
      _isSyncing = true;
      _statusError = null;
    });

    final manager = widget.syncRunner == null
        ? SyncManager(gatewayUrl: mapNetGateway)
        : null;
    try {
      final result = await (widget.syncRunner ?? manager!.executeSync)();
      final summary = await _summaryLoader();
      if (!mounted) return;
      setState(() {
        _lastResult = result;
        _summary = summary;
        _isOnline = result.success;
        _statusError = result.error;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _isOnline = false;
        _statusError = 'Synchronisation impossible : $error';
      });
    } finally {
      manager?.close();
      if (mounted) {
        setState(() => _isSyncing = false);
      }
    }
  }

  String _formatDate(DateTime? value) {
    if (value == null) return 'Jamais';
    final local = value.toLocal();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(local.day)}/${two(local.month)}/${local.year} '
        '${two(local.hour)}:${two(local.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    final summary = _summary;
    return Scaffold(
      appBar: AppBar(
        title: const Text('MapNet Data Mule'),
        actions: [
          IconButton(
            tooltip: 'Actualiser le statut',
            onPressed: _isLoading || _isSyncing ? null : _refreshStatus,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refreshStatus,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            _ConnectionBanner(isOnline: _isOnline),
            const SizedBox(height: 16),
            Text(
              'État hors-ligne',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            if (_isLoading)
              const Center(child: CircularProgressIndicator())
            else ...[
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 1.35,
                children: [
                  _MetricCard(
                    label: 'Carte locale',
                    value: 'v${summary?.localVersion ?? 0}',
                    icon: Icons.map_outlined,
                  ),
                  _MetricCard(
                    label: 'Version serveur',
                    value: summary == null || summary.serverVersion == 0
                        ? 'Inconnue'
                        : 'v${summary.serverVersion}',
                    icon: Icons.cloud_outlined,
                  ),
                  _MetricCard(
                    label: 'Routes locales',
                    value: '${summary?.roadCount ?? 0}',
                    icon: Icons.route_outlined,
                  ),
                  _MetricCard(
                    label: 'Télémétries en attente',
                    value: '${summary?.pendingTelemetryCount ?? 0}',
                    icon: Icons.upload_file_outlined,
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.schedule),
                  title: const Text('Dernière synchronisation'),
                  subtitle: Text(_formatDate(summary?.lastSyncAt)),
                  trailing: summary?.isCurrent == true
                      ? const Chip(label: Text('À jour'))
                      : const Chip(label: Text('À synchroniser')),
                ),
              ),
            ],
            if (_lastResult != null) ...[
              const SizedBox(height: 8),
              Card(
                color: _lastResult!.success
                    ? Theme.of(context).colorScheme.primaryContainer
                    : Theme.of(context).colorScheme.errorContainer,
                child: ListTile(
                  leading: Icon(
                    _lastResult!.success
                        ? Icons.check_circle_outline
                        : Icons.error_outline,
                  ),
                  title: Text(
                    _lastResult!.success
                        ? '${_lastResult!.appliedChanges} modification(s) appliquée(s)'
                        : 'Mode hors-ligne maintenu',
                  ),
                  subtitle: Text(
                    _lastResult!.success
                        ? 'Carte locale v${_lastResult!.localVersion}'
                        : (_lastResult!.error ?? 'Erreur inconnue'),
                  ),
                ),
              ),
            ],
            if (_statusError != null) ...[
              const SizedBox(height: 8),
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: ListTile(
                  leading: const Icon(Icons.cloud_off),
                  title: const Text('Synchronisation indisponible'),
                  subtitle: Text(_statusError!),
                ),
              ),
            ],
            const SizedBox(height: 16),
            FilledButton.icon(
              key: const Key('syncButton'),
              onPressed: _isSyncing ? null : _synchronize,
              icon: _isSyncing
                  ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.sync),
              label: Text(
                _isSyncing ? 'Synchronisation…' : 'Synchroniser maintenant',
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Gateway : $mapNetGateway',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 6),
            Text(
              'Les données locales restent disponibles sans réseau.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _ConnectionBanner extends StatelessWidget {
  const _ConnectionBanner({required this.isOnline});

  final bool isOnline;

  @override
  Widget build(BuildContext context) {
    final color = isOnline ? Colors.green.shade700 : Colors.orange.shade800;
    return Semantics(
      label: isOnline ? 'Connexion en ligne' : 'Connexion hors ligne',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color),
        ),
        child: Row(
          children: [
            Icon(isOnline ? Icons.cloud_done : Icons.cloud_off, color: color),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                isOnline
                    ? 'En ligne — synchronisation disponible'
                    : 'Hors ligne — données locales actives',
                style: TextStyle(color: color, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary),
            Text(value, style: Theme.of(context).textTheme.titleLarge),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
