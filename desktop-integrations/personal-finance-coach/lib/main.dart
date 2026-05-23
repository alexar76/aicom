import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:aicom_platform_init/aicom_platform_init.dart';
import 'package:aimarket_agent/aimarket_agent.dart';

import 'l10n/app_strings.dart';

const _appId = 'personal-finance-coach';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb) {
    initDatabaseFactory();
  }
  runApp(const FinanceCoachApp());
}

class FinanceCoachApp extends StatelessWidget {
  const FinanceCoachApp({super.key});

  @override
  Widget build(BuildContext context) {
    return AicomLocalizedApp(
      appId: _appId,
      appStrings: AppStrings.catalog,
      collectBackupData: () async => {
        'preferences': await collectPreferencesBackup(_appId),
      },
      restoreBackupData: (data) async {
        final prefs = data['preferences'];
        if (prefs is Map) await restorePreferencesBackup(Map<String, dynamic>.from(prefs));
      },
      builder: (context, locale) => MaterialApp(
        title: context.t('appTitle'),
        locale: locale.activeFlutterLocale,
        supportedLocales: AicomLocalization.localesFor(locale),
        localizationsDelegates: AicomLocalization.delegates,
        theme: AicomDesktopTheme.light(seed: AicomProductColors.personalFinance),
        darkTheme: AicomDesktopTheme.dark(seed: AicomProductColors.personalFinance),
        themeMode: ThemeMode.system,
        home: const FinanceHome(),
      ),
    );
  }
}

class FinanceHome extends StatefulWidget {
  const FinanceHome({super.key});

  @override
  State<FinanceHome> createState() => _FinanceHomeState();
}

class _FinanceHomeState extends State<FinanceHome> {
  int _index = 0;
  final _walletKey = walletKeyFromEnvironment();
  late final HubSession _hub;

  @override
  void initState() {
    super.initState();
    _hub = HubSession(affiliate: _appId, walletKey: _walletKey);
    if (_walletKey != null) _hub.connect();
  }

  @override
  void dispose() {
    _hub.dispose();
    super.dispose();
  }

  AimarketAgent? get _agent => _hub.isConnected ? _hub.agent : null;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          MarketplaceEconomicsBar(
            hubLabel: _hub.isConnected ? _hub.hubUrl : 'Hub offline',
            walletConfigured: _walletKey != null,
            channelBalanceUsd: _hub.channelBalanceUsd,
            sessionSpendUsd: _hub.sessionSpendUsd,
          ),
          Expanded(
            child: Row(
              children: [
                NavigationRail(
                  selectedIndex: _index,
                  labelType: NavigationRailLabelType.all,
                  onDestinationSelected: (i) => setState(() => _index = i),
                  destinations: [
                    NavigationRailDestination(icon: const Icon(Icons.dashboard), label: Text(context.t('navOverview'))),
                    NavigationRailDestination(icon: const Icon(Icons.upload_file), label: Text(context.t('navImport'))),
                    NavigationRailDestination(icon: const Icon(Icons.store), label: Text(context.t('navMarketplace'))),
                    NavigationRailDestination(icon: const Icon(Icons.shield), label: Text(context.t('navPrivacy'))),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(
                  child: IndexedStack(
                    index: _index,
                    children: [
                      _DashboardTab(agent: _agent),
                      const _ImportTab(),
                      _MarketplaceTab(agent: _agent),
                      const _PrivacyTab(),
                    ],
                  ),
                ),
                const Padding(
                  padding: EdgeInsets.only(right: 8),
                  child: AicomSettingsButton(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DashboardTab extends StatelessWidget {
  final AimarketAgent? agent;
  const _DashboardTab({required this.agent});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(context.t('financialOverview'), style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text(
          agent != null ? 'Marketplace connected · local SQLite vault' : 'Connect wallet to buy tax rules & categorizers',
          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 20),
        Row(
          children: [
            Expanded(child: _MetricCard(label: 'Net worth', value: '—', delta: '', icon: Icons.account_balance)),
            const SizedBox(width: 12),
            Expanded(child: _MetricCard(label: 'Monthly burn', value: '—', delta: '', icon: Icons.trending_down)),
            const SizedBox(width: 12),
            Expanded(child: _MetricCard(label: 'Savings rate', value: '—', delta: '', icon: Icons.savings)),
          ],
        ),
        const SizedBox(height: 20),
        Card(
          child: ListTile(
            leading: const Icon(Icons.auto_awesome),
            title: const Text('Import transactions to begin'),
            subtitle: const Text('Local SQLite vault · marketplace categorizers after import'),
            trailing: FilledButton(onPressed: () {}, child: const Text('Import')),
          ),
        ),
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.label, required this.value, required this.delta, required this.icon});

  final String label;
  final String value;
  final String delta;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: theme.colorScheme.primary),
            const SizedBox(height: 8),
            Text(value, style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
            Text(label, style: theme.textTheme.bodySmall),
            Text(delta, style: TextStyle(color: theme.colorScheme.primary, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

class _ImportTab extends StatelessWidget {
  const _ImportTab();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.upload_file, size: 64, color: theme.colorScheme.primary),
            const SizedBox(height: 16),
            Text('Import bank CSVs', style: theme.textTheme.headlineSmall),
            const SizedBox(height: 8),
            const Text('Parsed on-device. Never uploaded to cloud.'),
            const SizedBox(height: 24),
            FilledButton.icon(onPressed: () {}, icon: const Icon(Icons.folder_open), label: const Text('Choose CSV')),
          ],
        ),
      ),
    );
  }
}

class _MarketplaceTab extends StatelessWidget {
  final AimarketAgent? agent;
  const _MarketplaceTab({required this.agent});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text('Finance Marketplace', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
        const SizedBox(height: 16),
        _MarketCard(title: 'US Tax Rules 2026', price: 0.25, description: 'Federal + state tax rules for freelancers'),
        _MarketCard(title: 'ML Categorizer v3', price: 0.10, description: 'Auto-tags transactions from merchant descriptions'),
        _MarketCard(title: 'Investment Benchmarks Q2', price: 0.50, description: 'Portfolio comparison by age bracket'),
      ],
    );
  }
}

class _MarketCard extends StatelessWidget {
  final String title;
  final double price;
  final String description;
  const _MarketCard({required this.title, required this.price, required this.description});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(title),
        subtitle: Text(description),
        trailing: ElevatedButton(
          onPressed: () {},
          child: Text('\$${price.toStringAsFixed(2)}'),
        ),
      ),
    );
  }
}

class _PrivacyTab extends StatelessWidget {
  const _PrivacyTab();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.shield, size: 64, color: Colors.teal),
          const SizedBox(height: 16),
          Text(context.t('privacyNeverLeaves'), style: const TextStyle(fontSize: 16)),
          SizedBox(height: 8),
          Text('Only anonymized cohort patterns are shared.',
              style: TextStyle(color: Colors.grey)),
        ],
      ),
    );
  }
}
