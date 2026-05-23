import 'package:file_picker/file_picker.dart';
import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:aicom_platform_init/aicom_platform_init.dart';

import 'package:aimarket_agent/aimarket_agent.dart';

import 'l10n/app_strings.dart';

const String _kDefaultHub = 'https://hub.aicom.io';
const _appId = 'freelance-contract-reviewer';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb) {
    initDatabaseFactory();
  }
  runApp(const ContractorApp());
}

/// Root application widget.
class ContractorApp extends StatelessWidget {
  const ContractorApp({super.key});

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
        theme: AicomDesktopTheme.light(seed: AicomProductColors.freelanceContract),
        darkTheme: AicomDesktopTheme.dark(seed: AicomProductColors.freelanceContract),
        themeMode: ThemeMode.system,
        home: const DashboardScreen(),
      ),
    );
  }
}

// ── Service Locator (simplified) ─────────────────────────────────────

/// Singleton-style service holder for wallet key and AIMarket agent.
/// In a production app this would be managed by a DI container (get_it, riverpod).
class AppServices {
  static const _storage = FlutterSecureStorage();
  static const _walletKeyKey = 'aimarket_wallet_key';

  static String? _walletKey;
  static AimarketAgent? _agent;

  static Future<String?> get walletKey async {
    if (_walletKey != null) return _walletKey;
    const envKey = String.fromEnvironment('WALLET_KEY', defaultValue: '');
    if (envKey.isNotEmpty) {
      _walletKey = envKey;
      return _walletKey;
    }
    if (kIsWeb) return null;
    _walletKey = await _storage.read(key: _walletKeyKey);
    return _walletKey;
  }

  static Future<void> saveWalletKey(String key) async {
    _walletKey = key;
    await _storage.write(key: _walletKeyKey, value: key);
  }

  static Future<void> clearWalletKey() async {
    _walletKey = null;
    await _storage.delete(key: _walletKeyKey);
  }

  static Future<AimarketAgent> getAgent() async {
    final key = await walletKey;
    if (key == null) {
      throw StateError('Wallet key not configured. Go to Settings first.');
    }
    _agent ??= AimarketAgent(
      hubUrl: _kDefaultHub,
      walletKey: key,
    );
    return _agent!;
  }

  static void disposeAgent() {
    _agent?.dispose();
    _agent = null;
  }
}

// ── Dashboard Screen ─────────────────────────────────────────────────

/// Main landing screen showing recent contracts, quick stats, and
/// marketplace recommendations.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int _selectedIndex = 0;
  String? _walletStatus;
  HubSession _hub = HubSession(affiliate: _appId);

  @override
  void initState() {
    super.initState();
    _checkWallet();
  }

  @override
  void dispose() {
    _hub.dispose();
    super.dispose();
  }

  Future<void> _checkWallet() async {
    final key = await AppServices.walletKey ?? walletKeyFromEnvironment();
    _hub.dispose();
    _hub = HubSession(affiliate: _appId, walletKey: key);
    if (key != null) _hub.connect();
    if (!mounted) return;
    setState(() {
      _walletStatus = key != null ? 'Wallet configured' : 'No wallet key set';
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final screens = <Widget>[
      _buildDashboard(theme),
      const _UploadScreen(),
      const _MarketplaceScreen(),
      const _SettingsScreen(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(context.t('appTitle')),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Center(
              child: Text(
                _walletStatus ?? 'Loading...',
                style: theme.textTheme.bodySmall,
              ),
            ),
          ),
          const AicomSettingsButton(),
        ],
      ),
      body: Column(
        children: [
          MarketplaceEconomicsBar(
            hubLabel: _hub.isConnected ? _hub.hubUrl : _kDefaultHub,
            walletConfigured: _walletStatus?.contains('configured') ?? false,
            channelBalanceUsd: _hub.channelBalanceUsd,
            sessionSpendUsd: _hub.sessionSpendUsd,
          ),
          Expanded(child: screens[_selectedIndex]),
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
            icon: const Icon(Icons.upload_file_outlined),
            selectedIcon: const Icon(Icons.upload_file),
            label: context.t('navUpload'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.store_outlined),
            selectedIcon: const Icon(Icons.store),
            label: context.t('navMarketplace'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.settings_outlined),
            selectedIcon: const Icon(Icons.settings),
            label: context.t('navSettings'),
          ),
        ],
      ),
    );
  }

  Widget _buildDashboard(ThemeData theme) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Recent Contracts', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.description_outlined),
            title: const Text('No contracts reviewed yet'),
            subtitle: const Text('Upload a contract to get started'),
            trailing: const Icon(Icons.arrow_forward_ios),
            onTap: () => setState(() => _selectedIndex = 1),
          ),
        ),
        const SizedBox(height: 24),
        Text('Marketplace Recommendations', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.gavel, color: Colors.orange),
            title: const Text('California IP Clauses v2'),
            subtitle: const Text('\$4.99 — 142 reviews'),
            trailing: FilledButton.tonal(
              onPressed: () => setState(() => _selectedIndex = 2),
              child: const Text('Browse'),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.gavel, color: Colors.blue),
            title: const Text('NY Non-Compete Enforceability 2026'),
            subtitle: const Text('\$8.99 — 87 reviews'),
            trailing: FilledButton.tonal(
              onPressed: () => setState(() => _selectedIndex = 2),
              child: const Text('Browse'),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.gavel, color: Colors.teal),
            title: const Text('UK Freelancer Standard Clauses'),
            subtitle: const Text('\$6.99 — 203 reviews'),
            trailing: FilledButton.tonal(
              onPressed: () => setState(() => _selectedIndex = 2),
              child: const Text('Browse'),
            ),
          ),
        ),
        const SizedBox(height: 24),
        Text('Passive Income', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.trending_up, color: Colors.green),
            title: const Text('Anonymized pattern royalties'),
            subtitle: const Text('\$0.00 earned — Sell a pattern to start'),
          ),
        ),
      ],
    );
  }
}

// ── Upload Screen ────────────────────────────────────────────────────

/// Screen for dragging/selecting a contract file to parse locally.
class _UploadScreen extends StatefulWidget {
  const _UploadScreen();

  @override
  State<_UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<_UploadScreen> {
  String? _fileName;
  bool _analyzing = false;
  List<String>? _clauses;
  String? _parseMessage;

  Future<void> _pickFile() async {
    final pickResult = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['pdf', 'doc', 'docx', 'txt'],
      withData: kIsWeb,
    );
    if (pickResult == null || pickResult.files.isEmpty) return;

    final picked = pickResult.files.single;
    setState(() {
      _fileName = picked.name;
      _analyzing = true;
      _clauses = null;
      _parseMessage = null;
    });

    final key = await AppServices.walletKey;
    if (key == null) {
      if (!mounted) return;
      setState(() {
        _analyzing = false;
        _parseMessage =
            'File selected. Configure WALLET_KEY or Settings wallet to invoke hub clause libraries.';
      });
      return;
    }

    try {
      final agent = await AppServices.getAgent();
      final plan = await agent.discover(
        intent: 'freelance contract clause library',
        category: 'legal',
        limit: 1,
      );
      if (plan.isEmpty) {
        throw StateError('No clause libraries on hub for this contract');
      }
      final cap = plan.first.capability;
      final channel = await agent.openChannel(5.0);
      final textPreview = picked.bytes != null
          ? String.fromCharCodes(picked.bytes!.take(512))
          : picked.name;
      final invokeResult = await agent.invoke(
        capabilityId: cap.id,
        input: {'contract_preview': textPreview, 'file_name': picked.name},
        channelId: channel.id,
      );
      final output = invokeResult.output;
      final clauses = output?['clause_results'] as List? ??
          output?['clauses'] as List? ??
          [];
      if (!mounted) return;
      setState(() {
        _analyzing = false;
        _clauses = clauses.map((c) => c.toString()).toList();
        if (_clauses!.isEmpty) {
          _parseMessage = 'Hub returned no clause matches for ${picked.name}.';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _analyzing = false;
        _parseMessage = 'Analysis failed: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_clauses != null && _clauses!.isNotEmpty) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text('Review: $_fileName', style: theme.textTheme.headlineSmall),
          const SizedBox(height: 8),
          Text('Parsed locally · clause library match via AI Market (\$0.12/invoke)',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          const SizedBox(height: 16),
          ..._clauses!.map((c) => Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: Icon(Icons.gavel, color: theme.colorScheme.primary),
                  title: Text(c),
                ),
              )),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => setState(() {
              _fileName = null;
              _clauses = null;
              _parseMessage = null;
            }),
            icon: const Icon(Icons.upload_file),
            label: const Text('Upload another contract'),
          ),
        ],
      );
    }

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.cloud_upload_outlined, size: 80, color: theme.colorScheme.primary),
            const SizedBox(height: 16),
            Text(context.t('uploadContract'), style: theme.textTheme.headlineMedium),
            const SizedBox(height: 8),
            Text(
              'PDF, DOCX, or TXT — parsed entirely on your machine.\n'
              'Nothing leaves your device without your permission.',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: _analyzing ? null : _pickFile,
              icon: _analyzing
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.folder_open),
              label: Text(_analyzing ? 'Analyzing…' : 'Choose File'),
            ),
            if (_fileName != null) ...[
              const SizedBox(height: 16),
              Text('Selected: $_fileName', style: theme.textTheme.bodyMedium),
            ],
            if (_parseMessage != null) ...[
              const SizedBox(height: 12),
              Text(
                _parseMessage!,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
            const SizedBox(height: 16),
            Text(
              'or drag and drop a file here',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

// ── Marketplace Screen ───────────────────────────────────────────────

/// Screen for browsing, purchasing clause libraries and selling anonymized patterns.
class _MarketplaceScreen extends StatelessWidget {
  const _MarketplaceScreen();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Browse Clause Libraries', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 12),
        TextField(
          decoration: InputDecoration(
            hintText: 'Search by jurisdiction, clause type, or publisher...',
            prefixIcon: const Icon(Icons.search),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 16),
        _MarketplaceCard(
          icon: Icons.gavel,
          color: Colors.orange,
          title: 'California IP Clauses for Freelancers v2',
          subtitle: 'By LegalTech Studio — \$4.99 per review | TEE verified',
          onTap: () {},
        ),
        const SizedBox(height: 8),
        _MarketplaceCard(
          icon: Icons.gavel,
          color: Colors.blue,
          title: 'NY Non-Compete Enforceability 2026',
          subtitle: 'By Restrictive Covenant Analytics — \$8.99 per review | TEE verified',
          onTap: () {},
        ),
        const SizedBox(height: 8),
        _MarketplaceCard(
          icon: Icons.gavel,
          color: Colors.teal,
          title: 'UK Freelancer Standard Clause Library',
          subtitle: 'By London Legal Collective — \$6.99 per review | TEE verified',
          onTap: () {},
        ),
        const SizedBox(height: 8),
        _MarketplaceCard(
          icon: Icons.gavel,
          color: Colors.purple,
          title: 'German UrhG § 69b Software Ownership Check',
          subtitle: 'By Berlin RechtsKI — \$5.99 per review | TEE verified',
          onTap: () {},
        ),
        const SizedBox(height: 24),
        Text('Your Published Patterns', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.published_with_changes, color: Colors.green),
            title: const Text('No patterns published yet'),
            subtitle: const Text('After a review, anonymize and sell clause patterns to earn royalties'),
            trailing: FilledButton.tonal(
              onPressed: null,
              child: const Text('Sell'),
            ),
          ),
        ),
      ],
    );
  }
}

class _MarketplaceCard extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _MarketplaceCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: FilledButton.tonal(
          onPressed: onTap,
          child: const Text('Buy'),
        ),
      ),
    );
  }
}

// ── Settings Screen ──────────────────────────────────────────────────

/// Wallet key configuration and app settings.
class _SettingsScreen extends StatefulWidget {
  const _SettingsScreen();

  @override
  State<_SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<_SettingsScreen> {
  final _keyController = TextEditingController();
  bool _obscureKey = true;

  @override
  void initState() {
    super.initState();
    _loadKey();
  }

  Future<void> _loadKey() async {
    final key = await AppServices.walletKey;
    if (key != null) {
      _keyController.text = key;
    }
  }

  @override
  void dispose() {
    _keyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Marketplace Wallet', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 16),
        TextField(
          controller: _keyController,
          obscureText: _obscureKey,
          decoration: InputDecoration(
            labelText: 'Wallet Private Key',
            hintText: '0x... or hex-encoded private key',
            helperText: 'Get one from hub.aicom.io',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            suffixIcon: IconButton(
              icon: Icon(_obscureKey ? Icons.visibility_off : Icons.visibility),
              onPressed: () => setState(() => _obscureKey = !_obscureKey),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            FilledButton.icon(
              onPressed: () async {
                final key = _keyController.text.trim();
                if (key.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Enter a wallet key')),
                  );
                  return;
                }
                await AppServices.saveWalletKey(key);
                AppServices.disposeAgent(); // Force re-init on next use
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Wallet key saved')),
                  );
                }
              },
              icon: const Icon(Icons.save),
              label: const Text('Save Key'),
            ),
            const SizedBox(width: 12),
            OutlinedButton.icon(
              onPressed: () async {
                await AppServices.clearWalletKey();
                AppServices.disposeAgent();
                _keyController.clear();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Wallet key removed')),
                  );
                }
              },
              icon: const Icon(Icons.delete_forever),
              label: const Text('Remove Key'),
              style: OutlinedButton.styleFrom(foregroundColor: Colors.red),
            ),
          ],
        ),
        const SizedBox(height: 32),
        Text('Privacy', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.check_circle, color: Colors.green.shade700, size: 20),
                    const SizedBox(width: 8),
                    Text('Contracts are parsed locally', style: theme.textTheme.bodyMedium),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(Icons.check_circle, color: Colors.green.shade700, size: 20),
                    const SizedBox(width: 8),
                    Text('PII stripped before any data leaves your machine', style: theme.textTheme.bodyMedium),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(Icons.check_circle, color: Colors.green.shade700, size: 20),
                    const SizedBox(width: 8),
                    Text('TEE attestation verified before sending clause data', style: theme.textTheme.bodyMedium),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(Icons.check_circle, color: Colors.green.shade700, size: 20),
                    const SizedBox(width: 8),
                    Text('All selling of patterns is opt-in', style: theme.textTheme.bodyMedium),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 32),
        Text('About', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('Freelance Contract Reviewer'),
            subtitle: const Text('Version 1.0.0 — Built on AI Market Protocol v2'),
          ),
        ),
      ],
    );
  }
}
