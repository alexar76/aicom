import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:aicom_platform_init/aicom_platform_init.dart';

import 'package:aimarket_agent/aimarket_agent.dart';

import 'l10n/app_strings.dart';

const _appId = 'discovery-prospector';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb) {
    initDatabaseFactory();
  }
  runApp(const DiscoveryProspectorApp());
}

/// Root application widget.
class DiscoveryProspectorApp extends StatelessWidget {
  const DiscoveryProspectorApp({super.key});

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
        theme: AicomDesktopTheme.light(seed: AicomProductColors.discoveryProspector),
        darkTheme: AicomDesktopTheme.dark(seed: AicomProductColors.discoveryProspector),
        themeMode: ThemeMode.system,
        home: const DashboardPage(),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Data Models
// ═══════════════════════════════════════════════════════════════════════════════

/// A detected market gap — a niche with demand but insufficient supply.
class GapInsight {
  final String id;
  final String niche;
  final String category;
  final String subCategory;
  final double demandScore;
  final int supplyCount;
  final double supplyScarcity;
  final double nicheScore;
  final int estimatedMonthlySearches;
  final int estimatedMonthlyPurchaseAttempts;
  final double avgPriceWillingToPayUsd;
  final double estimatedMonthlyMarketUsd;
  final double growthVelocity;
  final String suggestedCapabilityType;

  const GapInsight({
    required this.id,
    required this.niche,
    required this.category,
    required this.subCategory,
    required this.demandScore,
    required this.supplyCount,
    required this.supplyScarcity,
    required this.nicheScore,
    required this.estimatedMonthlySearches,
    required this.estimatedMonthlyPurchaseAttempts,
    required this.avgPriceWillingToPayUsd,
    required this.estimatedMonthlyMarketUsd,
    required this.growthVelocity,
    required this.suggestedCapabilityType,
  });

  factory GapInsight.fromJson(Map<String, dynamic> json) {
    return GapInsight(
      id: json['insight_id'] as String? ?? '',
      niche: json['niche'] as String? ?? '',
      category: json['category'] as String? ?? '',
      subCategory: json['sub_category'] as String? ?? '',
      demandScore: (json['demand_score'] as num?)?.toDouble() ?? 0,
      supplyCount: json['supply_count'] as int? ?? 0,
      supplyScarcity: (json['supply_scarcity'] as num?)?.toDouble() ?? 0,
      nicheScore: (json['niche_score'] as num?)?.toDouble() ?? 0,
      estimatedMonthlySearches: json['estimated_monthly_searches'] as int? ?? 0,
      estimatedMonthlyPurchaseAttempts:
          json['estimated_monthly_purchase_attempts'] as int? ?? 0,
      avgPriceWillingToPayUsd:
          (json['average_price_willing_to_pay_usd'] as num?)?.toDouble() ?? 0,
      estimatedMonthlyMarketUsd:
          (json['estimated_monthly_market_usd'] as num?)?.toDouble() ?? 0,
      growthVelocity: (json['growth_velocity'] as num?)?.toDouble() ?? 0,
      suggestedCapabilityType:
          json['suggested_capability_type'] as String? ?? '',
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Gap Detector Engine
// ═══════════════════════════════════════════════════════════════════════════════

/// Implements gap detection algorithm described in docs/architecture.md.
class GapDetector {
  static const double _gapThreshold = 0.35;
  static const int _maxDemand = 500;
  static const int _maxSupply = 50;

  /// Compute gap score for a telemetry data point.
  static (double demandScore, double supplyScarcity, double gapScore) score(
    int searchCount,
    int purchaseAttempts,
    int supplyCount,
  ) {
    final demand = (searchCount + purchaseAttempts).toDouble();
    final demandScore = (demand / _maxDemand).clamp(0.0, 1.0);
    final supplyScarcity = supplyCount == 0
        ? 1.0
        : (1.0 - (supplyCount / _maxSupply).clamp(0.0, 1.0));
    final gapScore = demandScore * supplyScarcity;
    return (demandScore, supplyScarcity, gapScore);
  }

  /// Detect gaps from a list of raw telemetry entries.
  static List<GapInsight> detect(List<Map<String, dynamic>> telemetryEntries) {
    final gaps = <GapInsight>[];

    for (final entry in telemetryEntries) {
      final searchCount = entry['search_count'] as int? ?? 0;
      final purchaseAttempts = entry['purchase_attempts'] as int? ?? 0;
      final supplyCount = entry['supply_count'] as int? ?? 0;
      final supplyOnly = entry['supply_only'] as bool? ?? false;

      if (supplyOnly && searchCount == 0 && purchaseAttempts == 0) {
        if (supplyCount > 3) continue;
        final supplyScarcity = supplyCount == 0
            ? 1.0
            : (1.0 - (supplyCount / _maxSupply).clamp(0.0, 1.0));
        final avgPrice =
            (entry['avg_price_willing_to_pay_usd'] as num?)?.toDouble() ?? 0.10;
        gaps.add(GapInsight(
          id: 'gap-${DateTime.now().millisecondsSinceEpoch}-${gaps.length}',
          niche:
              '${entry['sub_category'] ?? 'unknown'} in ${entry['category'] ?? 'unknown'}',
          category: entry['category'] as String? ?? '',
          subCategory: entry['sub_category'] as String? ?? '',
          demandScore: 0,
          supplyCount: supplyCount,
          supplyScarcity: supplyScarcity,
          nicheScore: supplyScarcity,
          estimatedMonthlySearches: 0,
          estimatedMonthlyPurchaseAttempts: 0,
          avgPriceWillingToPayUsd: avgPrice,
          estimatedMonthlyMarketUsd: 0,
          growthVelocity: 0,
          suggestedCapabilityType:
              entry['suggested_type'] as String? ?? 'function',
        ));
        continue;
      }

      if (searchCount == 0 && purchaseAttempts == 0) continue;

      final (demandScore, supplyScarcity, gapScore) =
          score(searchCount, purchaseAttempts, supplyCount);

      if (gapScore < _gapThreshold) continue;

      final avgPrice =
          (entry['avg_price_willing_to_pay_usd'] as num?)?.toDouble() ?? 0.10;
      final growthVelocity =
          (entry['growth_velocity'] as num?)?.toDouble() ?? 0;

      final nicheScore = _computeNicheScore(
        demandScore: demandScore,
        supplyScarcity: supplyScarcity,
        estimatedMarket: (searchCount + purchaseAttempts) * avgPrice,
        growthVelocity: growthVelocity,
      );

      gaps.add(GapInsight(
        id: 'gap-${DateTime.now().millisecondsSinceEpoch}-${gaps.length}',
        niche: '${entry['sub_category'] ?? 'unknown'} in ${entry['category'] ?? 'unknown'}',
        category: entry['category'] as String? ?? '',
        subCategory: entry['sub_category'] as String? ?? '',
        demandScore: demandScore,
        supplyCount: supplyCount,
        supplyScarcity: supplyScarcity,
        nicheScore: nicheScore,
        estimatedMonthlySearches: searchCount,
        estimatedMonthlyPurchaseAttempts: purchaseAttempts,
        avgPriceWillingToPayUsd:
            (entry['avg_price_willing_to_pay_usd'] as num?)?.toDouble() ?? 0,
        estimatedMonthlyMarketUsd: (searchCount + purchaseAttempts) * avgPrice,
        growthVelocity: growthVelocity,
        suggestedCapabilityType: entry['suggested_type'] as String? ?? 'function',
      ));
    }

    gaps.sort((a, b) => b.nicheScore.compareTo(a.nicheScore));
    return gaps;
  }

  static double _computeNicheScore({
    required double demandScore,
    required double supplyScarcity,
    required double estimatedMarket,
    required double growthVelocity,
  }) {
    const maxMarket = 50000.0;
    final marketScore = (estimatedMarket / maxMarket).clamp(0.0, 1.0);
    const ecosystemFit = 0.5; // placeholder — would come from builder profile

    return 0.40 * demandScore +
        0.30 * supplyScarcity +
        0.15 * marketScore +
        0.10 * growthVelocity.clamp(0.0, 1.0) +
        0.05 * ecosystemFit;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Dashboard Page
// ═══════════════════════════════════════════════════════════════════════════════

/// Main dashboard showing detected gaps ranked by niche score.
class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  List<GapInsight> _gaps = [];
  GapInsight? _selectedGap;
  bool _loading = false;
  String? _error;
  String _activeCategory = 'all';
  final Set<String> _categories = {};
  late final HubSession _hub;
  final _walletKey = walletKeyFromEnvironment();

  static const _hubCategories = [
    'career',
    'finance',
    'health',
    'legal',
    'education',
    'marketing',
  ];

  @override
  void initState() {
    super.initState();
    _hub = HubSession(affiliate: _appId, walletKey: _walletKey);
    if (_walletKey != null) _hub.connect();
    _refresh();
  }

  @override
  void dispose() {
    _hub.dispose();
    super.dispose();
  }

  void _runGapDetection(List<Map<String, dynamic>> telemetry) {
    final gaps = GapDetector.detect(telemetry);
    setState(() {
      _gaps = gaps;
      _categories.clear();
      _categories.addAll(gaps.map((g) => g.category).toSet());
      if (_selectedGap != null &&
          !gaps.any((g) => g.id == _selectedGap!.id)) {
        _selectedGap = null;
      }
      if (_gaps.isNotEmpty && _selectedGap == null) {
        _selectedGap = _gaps.first;
      }
    });
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    if (_walletKey == null) {
      setState(() {
        _loading = false;
        _error = 'Configure WALLET_KEY to pull hub catalog';
        _gaps = [];
        _categories.clear();
        _selectedGap = null;
      });
      return;
    }

    try {
      final telemetry = <Map<String, dynamic>>[];
      final hubs = kIsWeb
          ? [kAicomLocalHubUrl, kAicomDefaultHubUrl]
          : [kAicomDefaultHubUrl, kAicomLocalHubUrl];

      for (final hubUrl in hubs) {
        try {
          final agent = AimarketAgent(
            hubUrl: hubUrl,
            walletKey: _walletKey!,
            affiliate: _appId,
          );
          for (final category in _hubCategories) {
            final plan = await agent.discover(
              intent: 'marketplace capabilities in $category with low supply',
              category: category,
              limit: 50,
            );
            final byProduct = <String, List<PlanStep>>{};
            for (final step in plan) {
              byProduct
                  .putIfAbsent(step.capability.productId, () => [])
                  .add(step);
            }
            for (final entry in byProduct.entries) {
              final steps = entry.value;
              final cap = steps.first.capability;
              telemetry.add({
                'category': category,
                'sub_category': entry.key,
                'search_count': 0,
                'purchase_attempts': 0,
                'supply_count': steps.length,
                'supply_only': true,
                'avg_price_willing_to_pay_usd': cap.pricePerCallUsd,
                'suggested_type': 'function',
              });
            }
          }
          agent.dispose();
          _hub.connect();
          _runGapDetection(telemetry);
          setState(() => _error = null);
          return;
        } catch (e) {
          _error = e.toString();
          continue;
        }
      }

      setState(() {
        _gaps = [];
        _categories.clear();
        _selectedGap = null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  List<GapInsight> get _filteredGaps {
    if (_activeCategory == 'all') return _gaps;
    return _gaps.where((g) => g.category == _activeCategory).toList();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(context.t('appTitle')),
        actions: [
          if (_selectedGap != null)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: FilledButton.icon(
                icon: const Icon(Icons.code, size: 18),
                label: const Text('Copy SDK Code'),
                onPressed: () => _copySdkCode(context, _selectedGap!),
              ),
            ),
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: IconButton(
              icon: _loading
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh),
              tooltip: context.t('refreshTelemetry'),
              onPressed: _loading ? null : _refresh,
            ),
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
          Expanded(
            child: _error != null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48),
                  const SizedBox(height: 16),
                  Text('Failed to load telemetry',
                      style: theme.textTheme.titleLarge),
                  const SizedBox(height: 8),
                  Text(_error!, style: theme.textTheme.bodySmall),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: _refresh,
                    child: const Text('Retry'),
                  ),
                ],
              ),
            )
          : _gaps.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.search_off, size: 64),
                      const SizedBox(height: 16),
                      Text('No underserved niches detected',
                          style: theme.textTheme.titleLarge),
                      const SizedBox(height: 8),
                      Text(
                        'Pull fresh telemetry to discover gaps',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(height: 16),
                      FilledButton(
                        onPressed: _refresh,
                        child: const Text('Refresh Telemetry'),
                      ),
                    ],
                  ),
                )
              : Row(
                  children: [
                    // ── Gap list panel ──
                    SizedBox(
                      width: 420,
                      child: Column(
                        children: [
                          // Category filter chips
                          Padding(
                            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
                            child: SizedBox(
                              height: 40,
                              child: ListView(
                                scrollDirection: Axis.horizontal,
                                children: [
                                  FilterChip(
                                    label: const Text('All'),
                                    selected: _activeCategory == 'all',
                                    onSelected: (_) =>
                                        setState(() => _activeCategory = 'all'),
                                  ),
                                  const SizedBox(width: 8),
                                  for (final cat in _categories)
                                    Padding(
                                      padding: const EdgeInsets.only(right: 8),
                                      child: FilterChip(
                                        label: Text(cat),
                                        selected: _activeCategory == cat,
                                        onSelected: (_) => setState(
                                            () => _activeCategory = cat),
                                      ),
                                    ),
                                ],
                              ),
                            ),
                          ),
                          const Divider(height: 1),
                          // Gap count
                          Padding(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 16, vertical: 8),
                            child: Row(
                              children: [
                                Text(
                                  '${_filteredGaps.length} gaps found',
                                  style: theme.textTheme.labelMedium?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  'Sorted by niche score',
                                  style: theme.textTheme.labelSmall?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          // Gap list
                          Expanded(
                            child: ListView.builder(
                              itemCount: _filteredGaps.length,
                              itemBuilder: (context, index) {
                                final gap = _filteredGaps[index];
                                final selected =
                                    _selectedGap?.id == gap.id;
                                return _GapListTile(
                                  gap: gap,
                                  selected: selected,
                                  onTap: () =>
                                      setState(() => _selectedGap = gap),
                                );
                              },
                            ),
                          ),
                        ],
                      ),
                    ),
                    const VerticalDivider(width: 1),
                    // ── Detail panel ──
                    Expanded(
                      child: _selectedGap != null
                          ? _GapDetailPanel(gap: _selectedGap!)
                          : Center(
                              child: Text(
                                'Select a gap to view details',
                                style: theme.textTheme.bodyLarge?.copyWith(
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ),
                    ),
                  ],
                ),
          ),
        ],
      ),
    );
  }

  void _copySdkCode(BuildContext context, GapInsight gap) {
    final code = '''
// --- Discovery Prospector: ${gap.niche} ---
// Demand score: ${(gap.demandScore * 100).toStringAsFixed(0)}%
// Supply count: ${gap.supplyCount}
// Est. monthly market: \$${gap.estimatedMonthlyMarketUsd.toStringAsFixed(0)}

final agent = AimarketAgent(
  hubUrl: 'https://hub.aicom.io',
  walletKey: walletKey,
);

// Open a channel to buy this gap insight
final channel = await agent.openChannel(1.00);

final insight = await agent.invoke(
  capabilityId: 'publish-gap-insight',
  input: {
    'niche': '${gap.niche}',
    'demand_score': ${gap.demandScore},
    'supply_count': ${gap.supplyCount},
    'category': '${gap.category}',
  },
  channelId: channel.id,
);

await agent.closeChannel(channel.id);
''';

    // Copy to clipboard would use Clipboard.setData in production.
    // For desktop, show a dialog with the code.
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('SDK Code — ${gap.niche}'),
        content: SizedBox(
          width: 500,
          child: SingleChildScrollView(
            child: SelectableText(
              code,
              style: const TextStyle(
                fontFamily: 'monospace',
                fontSize: 13,
              ),
            ),
          ),
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Gap List Tile
// ═══════════════════════════════════════════════════════════════════════════════

class _GapListTile extends StatelessWidget {
  final GapInsight gap;
  final bool selected;
  final VoidCallback onTap;

  const _GapListTile({
    required this.gap,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scorePercent = (gap.nicheScore * 100).toInt();
    final scoreColor = gap.nicheScore >= 0.7
        ? Colors.red
        : gap.nicheScore >= 0.5
            ? Colors.orange
            : Colors.amber;

    return ListTile(
      selected: selected,
      selectedTileColor:
          theme.colorScheme.primaryContainer.withOpacity(0.3),
      onTap: onTap,
      leading: CircleAvatar(
        backgroundColor: scoreColor.withOpacity(0.15),
        child: Text(
          '$scorePercent',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 13,
            color: scoreColor,
          ),
        ),
      ),
      title: Text(
        gap.niche,
        style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 14),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Row(
        children: [
          _ScoreBadge(
            label: '${gap.supplyCount}',
            tooltip: 'Supply count',
            color: gap.supplyCount == 0 ? Colors.red.shade300 : Colors.green.shade300,
          ),
          const SizedBox(width: 6),
          _ScoreBadge(
            label: '\$${gap.estimatedMonthlyMarketUsd.toStringAsFixed(0)}/mo',
            tooltip: 'Estimated monthly market',
            color: theme.colorScheme.tertiary,
          ),
        ],
      ),
      trailing: Icon(
        gap.suggestedCapabilityType == 'scoring-function'
            ? Icons.trending_up
            : gap.suggestedCapabilityType == 'generation'
                ? Icons.edit_note
                : Icons.category,
        size: 18,
        color: theme.colorScheme.onSurfaceVariant,
      ),
    );
  }
}

class _ScoreBadge extends StatelessWidget {
  final String label;
  final String tooltip;
  final Color color;

  const _ScoreBadge({
    required this.label,
    required this.tooltip,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: color.withOpacity(0.15),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w600,
            color: color,
          ),
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Gap Detail Panel
// ═══════════════════════════════════════════════════════════════════════════════

class _GapDetailPanel extends StatelessWidget {
  final GapInsight gap;

  const _GapDetailPanel({required this.gap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Text(
            gap.niche,
            style: theme.textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              _MetadataChip(
                label: gap.category,
                icon: Icons.folder_outlined,
              ),
              const SizedBox(width: 8),
              _MetadataChip(
                label: gap.subCategory,
                icon: Icons.tag,
              ),
              const SizedBox(width: 8),
              _MetadataChip(
                label: gap.suggestedCapabilityType,
                icon: Icons.build_outlined,
              ),
            ],
          ),
          const SizedBox(height: 24),

          // Demand score gauge
          _ScoreGauge(
            label: 'Niche Score',
            value: gap.nicheScore,
            color: gap.nicheScore >= 0.7
                ? Colors.red
                : gap.nicheScore >= 0.5
                    ? Colors.orange
                    : Colors.amber,
          ),
          const SizedBox(height: 24),

          // Metric cards
          Row(
            children: [
              Expanded(
                child: _MetricCard(
                  icon: Icons.search,
                  label: 'Monthly Searches',
                  value: gap.estimatedMonthlySearches.toString(),
                  color: theme.colorScheme.primary,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _MetricCard(
                  icon: Icons.shopping_cart_outlined,
                  label: 'Purchase Attempts',
                  value: gap.estimatedMonthlyPurchaseAttempts.toString(),
                  color: theme.colorScheme.secondary,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _MetricCard(
                  icon: Icons.inventory_2_outlined,
                  label: 'Supply Count',
                  value: gap.supplyCount.toString(),
                  color: gap.supplyCount == 0
                      ? Colors.red
                      : Colors.green,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          Row(
            children: [
              Expanded(
                child: _MetricCard(
                  icon: Icons.attach_money,
                  label: 'Est. Monthly Market',
                  value: '\$${gap.estimatedMonthlyMarketUsd.toStringAsFixed(0)}',
                  color: Colors.green.shade600,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _MetricCard(
                  icon: Icons.trending_up,
                  label: 'Growth Velocity',
                  value: '${(gap.growthVelocity * 100).toStringAsFixed(0)}%',
                  color: Colors.blue,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _MetricCard(
                  icon: Icons.price_check,
                  label: 'Avg Price Willing to Pay',
                  value: '\$${gap.avgPriceWillingToPayUsd.toStringAsFixed(2)}',
                  color: Colors.purple,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),

          // Score breakdown
          Text('Score Breakdown',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
              )),
          const SizedBox(height: 12),
          _ScoreBar(
            label: 'Demand Score',
            weight: '40%',
            value: gap.demandScore,
          ),
          _ScoreBar(
            label: 'Supply Scarcity',
            weight: '30%',
            value: gap.supplyScarcity,
          ),
          _ScoreBar(
            label: 'Market Potential',
            weight: '15%',
            value: (gap.estimatedMonthlyMarketUsd / 50000).clamp(0.0, 1.0),
          ),
          _ScoreBar(
            label: 'Growth Velocity',
            weight: '10%',
            value: gap.growthVelocity.clamp(0.0, 1.0),
          ),
          const SizedBox(height: 24),

          // Suggested capability
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: theme.colorScheme.primaryContainer.withOpacity(0.3),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: theme.colorScheme.primary.withOpacity(0.2),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.lightbulb_outline,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Suggested Capability',
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Build a ${gap.suggestedCapabilityType} for "${gap.subCategory}"',
                        style: theme.textTheme.bodyLarge?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Reusable Widgets
// ═══════════════════════════════════════════════════════════════════════════════

class _MetadataChip extends StatelessWidget {
  final String label;
  final IconData icon;

  const _MetadataChip({required this.label, required this.icon});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 4),
          Text(
            label,
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _ScoreGauge extends StatelessWidget {
  final String label;
  final double value;
  final Color color;

  const _ScoreGauge({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pct = (value * 100).toInt();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 60,
            height: 60,
            child: Stack(
              alignment: Alignment.center,
              children: [
                CircularProgressIndicator(
                  value: value,
                  strokeWidth: 6,
                  backgroundColor: color.withOpacity(0.15),
                  valueColor: AlwaysStoppedAnimation(color),
                ),
                Text(
                  '$pct',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 18,
                    color: color,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    )),
                const SizedBox(height: 4),
                Text(
                  value >= 0.7
                      ? 'Strong opportunity — build immediately'
                      : value >= 0.5
                          ? 'Moderate opportunity — consider building'
                          : 'Weak signal — monitor for growth',
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _MetricCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: color),
          const SizedBox(height: 8),
          Text(
            value,
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _ScoreBar extends StatelessWidget {
  final String label;
  final String weight;
  final double value;

  const _ScoreBar({
    required this.label,
    required this.weight,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(
            width: 140,
            child: Text(
              label,
              style: theme.textTheme.bodyMedium,
            ),
          ),
          SizedBox(
            width: 40,
            child: Text(
              weight,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: value,
                minHeight: 8,
                backgroundColor: theme.colorScheme.surfaceContainerHighest,
              ),
            ),
          ),
          SizedBox(
            width: 48,
            child: Text(
              '${(value * 100).toInt()}%',
              textAlign: TextAlign.right,
              style: theme.textTheme.labelSmall?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
