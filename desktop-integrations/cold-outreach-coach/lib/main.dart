import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:aicom_platform_init/aicom_platform_init.dart';
import 'package:aimarket_agent/aimarket_agent.dart';

import 'l10n/app_strings.dart';

const _appId = 'cold-outreach-coach';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb) {
    initDatabaseFactory();
  }
  runApp(const ColdOutreachCoachApp());
}

// ---------------------------------------------------------------------------
// App root
// ---------------------------------------------------------------------------

class ColdOutreachCoachApp extends StatelessWidget {
  const ColdOutreachCoachApp({super.key});

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
        debugShowCheckedModeBanner: false,
        locale: locale.activeFlutterLocale,
        supportedLocales: AicomLocalization.localesFor(locale),
        localizationsDelegates: AicomLocalization.delegates,
        theme: AicomDesktopTheme.light(seed: AicomProductColors.coldOutreach),
        darkTheme: AicomDesktopTheme.dark(seed: AicomProductColors.coldOutreach),
        themeMode: ThemeMode.system,
        home: const MainShell(),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Main navigation shell -- tabs for the five core workflows
// ---------------------------------------------------------------------------

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _selectedIndex = 0;
  final _walletKey = walletKeyFromEnvironment();
  late final HubSession _hub;

  static const _tabs = <Widget>[
    _DashboardTab(),
    _ComposerTab(),
    _DeliverabilityTab(),
    _AnalyticsTab(),
    _MarketplaceTab(),
  ];

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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.t('appTitle')),
        centerTitle: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.account_balance_wallet_outlined),
            tooltip: 'Marketplace Wallet',
            onPressed: () => _openWalletPanel(context),
          ),
          IconButton(
            icon: const Icon(Icons.info_outline),
            tooltip: 'Privacy notice',
            onPressed: () => _showPrivacyNotice(context),
          ),
          const AicomSettingsButton(),
        ],
      ),
      body: Column(
        children: [
          MarketplaceEconomicsBar(
            hubLabel: _hub.isConnected ? _hub.hubUrl : 'Hub offline',
            walletConfigured: _walletKey != null,
            channelBalanceUsd: _hub.channelBalanceUsd,
            sessionSpendUsd: _hub.sessionSpendUsd,
          ),
          Expanded(child: _tabs[_selectedIndex]),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (i) => setState(() => _selectedIndex = i),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.dashboard_outlined),
            selectedIcon: const Icon(Icons.dashboard),
            label: context.t('navDashboard'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.edit_outlined),
            selectedIcon: const Icon(Icons.edit),
            label: context.t('navComposer'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.shield_outlined),
            selectedIcon: const Icon(Icons.shield),
            label: context.t('navDeliverability'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.analytics_outlined),
            selectedIcon: const Icon(Icons.analytics),
            label: context.t('navAnalytics'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.store_outlined),
            selectedIcon: const Icon(Icons.store),
            label: context.t('navMarketplace'),
          ),
        ],
      ),
    );
  }

  void _openWalletPanel(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (_) => const _WalletPanel(),
    );
  }

  void _showPrivacyNotice(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Privacy first'),
        content: const Text(
          'Your email content never leaves this device. '
          'Only structural metrics (word count, paragraph count, '
          'question placement, link density, tone markers) are '
          'anonymized and published to the marketplace for '
          'reply-rate analytics.\n\n'
          'All AI Market Protocol calls use TEE-verified enclaves '
          'so the rules you purchase are executed in trusted hardware.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }
}

// ===================================================================
// TAB: Dashboard
// ===================================================================

class _DashboardTab extends StatelessWidget {
  const _DashboardTab();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Campaigns', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 12),
        _StatCard(
          icon: Icons.send,
          label: 'Emails sent this week',
          value: '0',
        ),
        const SizedBox(height: 8),
        _StatCard(
          icon: Icons.reply,
          label: 'Reply rate',
          value: '-- %',
        ),
        const SizedBox(height: 8),
        _StatCard(
          icon: Icons.shield,
          label: 'Deliverability score',
          value: '-- / 100',
        ),
        const SizedBox(height: 24),
        Text('Recent activity', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Center(
              child: Text(
                'Create your first campaign to get started.',
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _StatCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _StatCard({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon),
        title: Text(label),
        trailing: Text(
          value,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
        ),
      ),
    );
  }
}

// ===================================================================
// TAB: Composer
// ===================================================================

class _ComposerTab extends StatefulWidget {
  const _ComposerTab();

  @override
  State<_ComposerTab> createState() => _ComposerTabState();
}

class _ComposerTabState extends State<_ComposerTab> {
  final _subjectCtrl = TextEditingController();
  final _bodyCtrl = TextEditingController();
  String _selectedTemplate = 'None';

  static const _templates = [
    'None',
    'SaaS — Technical ICP',
    'SaaS — Executive ICP',
    'Freelance — Proposal intro',
    'Recruiter — Initial reach',
  ];

  @override
  void dispose() {
    _subjectCtrl.dispose();
    _bodyCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        DropdownButtonFormField<String>(
          value: _selectedTemplate,
          decoration: const InputDecoration(labelText: 'Template'),
          items: _templates
              .map((t) => DropdownMenuItem(value: t, child: Text(t)))
              .toList(),
          onChanged: (v) => setState(() => _selectedTemplate = v!),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _subjectCtrl,
          decoration: const InputDecoration(
            labelText: 'Subject line',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _bodyCtrl,
          maxLines: 12,
          decoration: const InputDecoration(
            labelText: 'Email body',
            border: OutlineInputBorder(),
            hintText:
                'Write your cold email here. Content stays on your device.',
          ),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            FilledButton.icon(
              onPressed: _analyze,
              icon: const Icon(Icons.auto_awesome),
              label: const Text('Analyze'),
            ),
            const SizedBox(width: 12),
            OutlinedButton.icon(
              onPressed: _scoreDeliverability,
              icon: const Icon(Icons.shield),
              label: const Text('Score deliverability'),
            ),
          ],
        ),
      ],
    );
  }

  void _analyze() {
    // Local-only: structural analysis
    // No content is sent to the network.
    final text = _bodyCtrl.text;
    if (text.trim().isEmpty) return;

    final words = text.split(RegExp(r'\s+')).length;
    final paras = text.split(RegExp(r'\n\s*\n')).length;
    final questions = '?'.allMatches(text).length;
    final links = RegExp(r'https?://').allMatches(text).length;

    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Structural Analysis (local only)'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Word count: $words'),
            Text('Paragraphs: $paras'),
            Text('Questions: $questions'),
            Text('Links: $links'),
            const SizedBox(height: 8),
            Text(
              'These structural metrics are the ONLY data that '
              'can be anonymously contributed to the marketplace.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  void _scoreDeliverability() {
    // Placeholder: calls marketplace via AimarketAgent.
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Deliverability scoring requires an active marketplace connection. '
          'Go to Marketplace tab to configure.',
        ),
      ),
    );
  }
}

// ===================================================================
// TAB: Deliverability
// ===================================================================

class _DeliverabilityTab extends StatelessWidget {
  const _DeliverabilityTab();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Deliverability Rules', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.info_outlined),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Deliverability rules change weekly as spam filters '
                        'evolve. The marketplace aggregates rules from '
                        'decentralized maintainers so you always have the '
                        'latest SPF, DKIM, and content heuristics.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Text('Active rules', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        _RuleTile(
          icon: Icons.dns_outlined,
          title: 'SPF record',
          subtitle: 'Ensure your sending domain has an SPF TXT record '
              'authorizing your SMTP server.',
          status: 'Unchecked',
        ),
        _RuleTile(
          icon: Icons.vpn_key_outlined,
          title: 'DKIM signature',
          subtitle: 'Sign outgoing emails with a 2048-bit DKIM key.',
          status: 'Unchecked',
        ),
        _RuleTile(
          icon: Icons.email_outlined,
          title: 'DMARC policy',
          subtitle: 'Set p=quarantine or p=reject to prevent spoofing.',
          status: 'Unchecked',
        ),
        _RuleTile(
          icon: Icons.wc_outlined,
          title: 'Warm-up schedule',
          subtitle: 'Gradually increase sending volume from a new domain.',
          status: 'Unchecked',
        ),
      ],
    );
  }
}

class _RuleTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final String status;

  const _RuleTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.status,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final statusColor = status == 'Pass'
        ? Colors.green
        : status == 'Fail'
            ? Colors.red
            : theme.colorScheme.onSurfaceVariant;

    return Card(
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: Chip(
          label: Text(status, style: TextStyle(color: statusColor)),
        ),
      ),
    );
  }
}

// ===================================================================
// TAB: Analytics
// ===================================================================

class _AnalyticsTab extends StatelessWidget {
  const _AnalyticsTab();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Reply-Rate Signals', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Anonymized structural insights from the marketplace. '
                  'No email content is ever shared — only aggregate metrics.',
                  style: theme.textTheme.bodyMedium,
                ),
                const SizedBox(height: 16),
                Text(
                  'Signal breakdown',
                  style: theme.textTheme.titleMedium,
                ),
                const Divider(),
                _SignalBar(
                  label: 'Word count (optimal 50-125)',
                  value: 0.0,
                ),
                _SignalBar(
                  label: 'Paragraphs (optimal 3-5)',
                  value: 0.0,
                ),
                _SignalBar(
                  label: 'Question placement',
                  value: 0.0,
                ),
                _SignalBar(
                  label: 'Personalization tokens',
                  value: 0.0,
                ),
                _SignalBar(
                  label: 'Link density',
                  value: 0.0,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _SignalBar extends StatelessWidget {
  final String label;
  final double value;

  const _SignalBar({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 2),
          LinearProgressIndicator(value: value),
        ],
      ),
    );
  }
}

// ===================================================================
// TAB: Marketplace
// ===================================================================

class _MarketplaceTab extends StatefulWidget {
  const _MarketplaceTab();

  @override
  State<_MarketplaceTab> createState() => _MarketplaceTabState();
}

class _MarketplaceTabState extends State<_MarketplaceTab> {
  final _walletKey = walletKeyFromEnvironment();
  final _intentCtrl = TextEditingController();
  AimarketAgent? _agent;
  String _status = 'Not connected';
  List<PlanStep> _results = [];

  @override
  void dispose() {
    _intentCtrl.dispose();
    _agent?.dispose();
    super.dispose();
  }

  void _connect() {
    if (_walletKey == null) {
      setState(() => _status = 'Configure WALLET_KEY to connect');
      return;
    }
    setState(() => _status = 'Wallet configured');
  }

  Future<void> _search() async {
    final intent = _intentCtrl.text.trim();
    if (intent.isEmpty) return;

    if (_walletKey == null) {
      setState(() => _status = 'Configure WALLET_KEY to search hub');
      return;
    }

    setState(() => _status = 'Searching...');

    try {
      final agent = AimarketAgent(
        hubUrl: kAicomDefaultHubUrl,
        walletKey: _walletKey!,
        affiliate: 'cold-outreach-coach',
      );

      final plan = await agent.discover(
        intent: intent,
        category: 'career',
        budget: 5.00,
      );

      setState(() {
        _agent = agent;
        _results = plan;
        _status =
            'Found ${plan.length} capabilities. Open a channel to invoke.';
      });
    } catch (e) {
      setState(() => _status = 'Error: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('AI Market Protocol v2', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          color: theme.colorScheme.primaryContainer,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Icon(Icons.circle, size: 10, color: _status.contains('Error')
                    ? Colors.red
                    : _status.contains('Connected') || _status.contains('Found')
                        ? Colors.green
                        : Colors.grey),
                const SizedBox(width: 8),
                Expanded(child: Text(_status)),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Text('Discover', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _intentCtrl,
                decoration: const InputDecoration(
                  labelText: 'What do you need?',
                  hintText:
                      'e.g. email deliverability rules for cold outreach Q2 2026',
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: _search,
              child: const Text('Search'),
            ),
            const SizedBox(width: 8),
            OutlinedButton(
              onPressed: _connect,
              child: const Text('Connect'),
            ),
          ],
        ),
        if (_results.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('Results', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final step in _results)
            Card(
              child: ListTile(
                leading: Icon(
                  Icons.check_circle_outline,
                  color: Colors.green,
                ),
                title: Text(step.capability.name),
                subtitle: Text(step.capability.description),
                trailing: Text(
                  '\$${step.capability.pricePerCallUsd.toStringAsFixed(2)}/call',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
        ],
      ],
    );
  }
}

// ===================================================================
// WALLET PANEL (bottom sheet)
// ===================================================================

class _WalletPanel extends StatelessWidget {
  const _WalletPanel();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Marketplace Wallet', style: theme.textTheme.titleLarge),
          const SizedBox(height: 16),
          const ListTile(
            leading: Icon(Icons.account_balance_wallet),
            title: Text('Balance'),
            trailing: Text('\$0.00'),
          ),
          const ListTile(
            leading: Icon(Icons.history),
            title: Text('Active channels'),
            trailing: Text('0'),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: () {},
            icon: const Icon(Icons.add),
            label: const Text('Open channel'),
          ),
        ],
      ),
    );
  }
}
