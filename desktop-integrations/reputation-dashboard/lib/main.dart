import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:aimarket_agent/aimarket_agent.dart';

import 'l10n/app_strings.dart';

const _appId = 'reputation-dashboard';

String? _walletKeyFromEnv() => walletKeyFromEnvironment();

void main() {
  runApp(const ReputationDashboardApp());
}

class ReputationDashboardApp extends StatelessWidget {
  const ReputationDashboardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return AicomLocalizedApp(
      appId: _appId,
      appStrings: AppStrings.catalog,
      collectBackupData: () async => {
        'preferences': await collectPreferencesBackup(_appId),
        'snapshot': 'reputation-v1',
      },
      restoreBackupData: (data) async {
        final prefs = data['preferences'];
        if (prefs is Map) {
          await restorePreferencesBackup(Map<String, dynamic>.from(prefs));
        }
      },
      builder: (context, locale) => MaterialApp(
        title: context.t('appTitle'),
        debugShowCheckedModeBanner: false,
        locale: locale.activeFlutterLocale,
        supportedLocales: AicomLocalization.localesFor(locale),
        localizationsDelegates: AicomLocalization.delegates,
        theme: AicomDesktopTheme.light(seed: AicomProductColors.reputation),
        darkTheme: AicomDesktopTheme.dark(seed: AicomProductColors.reputation),
        themeMode: ThemeMode.system,
        home: const DashboardHomePage(),
      ),
    );
  }
}

class _CapabilityReputation {
  final String name;
  final String category;
  final double trustScore;
  final int reviewCount;
  final double pricePerCall;
  final String seller;

  const _CapabilityReputation({
    required this.name,
    required this.category,
    required this.trustScore,
    required this.reviewCount,
    required this.pricePerCall,
    required this.seller,
  });
}

class _UserReview {
  final String capability;
  final int stars;
  final String excerpt;
  final String date;

  const _UserReview({
    required this.capability,
    required this.stars,
    required this.excerpt,
    required this.date,
  });

  Map<String, dynamic> toJson() => {
        'capability': capability,
        'stars': stars,
        'excerpt': excerpt,
        'date': date,
      };

  factory _UserReview.fromJson(Map<String, dynamic> j) => _UserReview(
        capability: j['capability'] as String? ?? '',
        stars: j['stars'] as int? ?? 0,
        excerpt: j['excerpt'] as String? ?? '',
        date: j['date'] as String? ?? '',
      );
}

class DashboardHomePage extends StatefulWidget {
  const DashboardHomePage({super.key});

  @override
  State<DashboardHomePage> createState() => _DashboardHomePageState();
}

class _DashboardHomePageState extends State<DashboardHomePage> {
  int _selectedIndex = 0;
  bool _loading = false;
  bool _hubLive = false;
  String? _hubError;
  List<_CapabilityReputation> _top = [];
  List<_UserReview> _reviews = [];
  late final HubSession _hub;
  final _walletKey = _walletKeyFromEnv();

  List<String> _titles(BuildContext context) => [
        context.t('titleTop'),
        context.t('titleReviews'),
        context.t('titleSeller'),
        context.t('titleCurator'),
      ];

  @override
  void initState() {
    super.initState();
    _hub = HubSession(
      affiliate: _appId,
      walletKey: _walletKey,
    );
    if (_walletKey != null) _hub.connect();
    _loadPersistedReviews();
    _refresh();
  }

  Future<void> _loadPersistedReviews() async {
    final prefs = await collectPreferencesBackup(_appId);
    final raw = prefs['reputation-dashboard:reviews'];
    if (raw is! List) return;
    if (!mounted) return;
    setState(() {
      _reviews = raw
          .whereType<Map>()
          .map((e) => _UserReview.fromJson(Map<String, dynamic>.from(e)))
          .toList();
    });
  }

  @override
  void dispose() {
    _hub.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_walletKey == null) {
      setState(() {
        _loading = false;
        _hubLive = false;
        _hubError = 'Configure WALLET_KEY to sync with hub';
        _top = [];
      });
      return;
    }

    setState(() {
      _loading = true;
      _hubError = null;
    });
    final hubs = kIsWeb
        ? [kAicomLocalHubUrl, kAicomDefaultHubUrl]
        : [kAicomDefaultHubUrl, kAicomLocalHubUrl];

    for (final url in hubs) {
      try {
        final agent = AimarketAgent(
          hubUrl: url,
          walletKey: _walletKey!,
          affiliate: _appId,
        );
        final plan = await agent.discover(
          intent: 'reputation scores for career category capabilities',
          category: 'career',
        );
        agent.dispose();
        if (!mounted) return;
        setState(() {
          _hubLive = true;
          _hubError = null;
          _top = plan
              .map(
                (s) => _CapabilityReputation(
                  name: s.capability.name,
                  category: 'career',
                  trustScore: s.capability.trustScore ?? 0.0,
                  reviewCount: 0,
                  pricePerCall: s.capability.pricePerCallUsd,
                  seller: s.capability.sourceHubName ?? s.capability.sourceHub,
                ),
              )
              .toList();
          _loading = false;
        });
        return;
      } catch (e) {
        _hubError = e.toString();
        continue;
      }
    }

    if (!mounted) return;
    setState(() {
      _hubLive = false;
      _top = [];
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles(context)[_selectedIndex]),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Sync',
            onPressed: _loading ? null : _refresh,
          ),
          const AicomSettingsButton(),
        ],
      ),
      body: Column(
        children: [
          MarketplaceEconomicsBar(
            hubLabel: _hubLive ? 'Hub live' : (_hubError ?? 'Hub offline'),
            walletConfigured: _walletKey != null,
            channelBalanceUsd: _hub.channelBalanceUsd,
            sessionSpendUsd: _hub.sessionSpendUsd,
            onConnect: _walletKey == null
                ? () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Set WALLET_KEY at build time or in Settings backup'),
                      ),
                    );
                  }
                : null,
          ),
          Expanded(child: _buildBody()),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (i) => setState(() => _selectedIndex = i),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.leaderboard_outlined),
            selectedIcon: const Icon(Icons.leaderboard),
            label: context.t('navTop'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.rate_review_outlined),
            selectedIcon: const Icon(Icons.rate_review),
            label: context.t('navReviews'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.store_outlined),
            selectedIcon: const Icon(Icons.store),
            label: context.t('navSeller'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.admin_panel_settings_outlined),
            selectedIcon: const Icon(Icons.admin_panel_settings),
            label: context.t('navCurator'),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_loading && _top.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    switch (_selectedIndex) {
      case 0:
        return _TopTab(items: _top, hubLive: _hubLive);
      case 1:
        return _ReviewsTab(reviews: _reviews);
      case 2:
        return const _SellerTab();
      case 3:
        return const _CuratorTab();
      default:
        return _TopTab(items: _top, hubLive: _hubLive);
    }
  }
}

class _TopTab extends StatelessWidget {
  const _TopTab({required this.items, required this.hubLive});

  final List<_CapabilityReputation> items;
  final bool hubLive;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (items.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.cloud_off, size: 48, color: theme.colorScheme.outline),
              const SizedBox(height: 12),
              Text(
                hubLive ? 'No capabilities in hub index yet' : 'Hub unreachable',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(
                hubLive
                    ? 'Run factory pipeline or seed capabilities on the hub.'
                    : 'Start local hub (127.0.0.1:8080) or check hub.aicom.io.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ),
      );
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        ...items.asMap().entries.map((e) {
          final i = e.key + 1;
          final row = e.value;
          return Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              leading: CircleAvatar(
                child: Text('#$i', style: const TextStyle(fontWeight: FontWeight.bold)),
              ),
              title: Text(row.name),
              subtitle: Text(
                '${row.category} · ${row.reviewCount} reviews · ${row.seller}',
              ),
              trailing: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.verified, size: 16, color: theme.colorScheme.primary),
                      const SizedBox(width: 4),
                      Text('${(row.trustScore * 100).round()}%'),
                    ],
                  ),
                  Text('\$${row.pricePerCall.toStringAsFixed(2)}/call',
                      style: theme.textTheme.labelSmall),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }
}

class _ReviewsTab extends StatelessWidget {
  const _ReviewsTab({required this.reviews});

  final List<_UserReview> reviews;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          context.t('titleReviews'),
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 12),
        if (reviews.isEmpty)
          Text(
            'No reviews yet. Submit after a verified purchase via hub.',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        ...reviews.map(
          (r) => Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              title: Text(r.capability),
              subtitle: Text('${r.date} — ${r.excerpt}'),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(
                  5,
                  (i) => Icon(
                    i < r.stars ? Icons.star : Icons.star_border,
                    size: 16,
                    color: Colors.amber.shade700,
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _SellerTab extends StatelessWidget {
  const _SellerTab();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'Seller metrics load from hub reputation API after wallet is configured.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyLarge,
        ),
      ),
    );
  }
}

class _CuratorTab extends StatelessWidget {
  const _CuratorTab();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'Moderation queue syncs from hub — no items pending.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyLarge,
        ),
      ),
    );
  }
}
