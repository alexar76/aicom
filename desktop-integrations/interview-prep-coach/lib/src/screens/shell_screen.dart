import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/marketplace_service.dart';
import '../widgets/marketplace_status_bar.dart';

/// Main shell screen with bottom navigation and scaffold.
class ShellScreen extends StatefulWidget {
  const ShellScreen({super.key});

  @override
  State<ShellScreen> createState() => _ShellScreenState();
}

class _ShellScreenState extends State<ShellScreen> {
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    final marketplace = context.read<MarketplaceService>();
    final balance = marketplace.channelBalance;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Interview Prep Coach'),
        actions: [
          const MarketplaceStatusBar(),
          const AicomSettingsButton(),
        ],
      ),
      body: Column(
        children: [
          _EconomicsStrip(balance: balance ?? 0.0),
          Expanded(child: _buildBody()),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (i) => setState(() => _selectedIndex = i),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.school_outlined),
            selectedIcon: const Icon(Icons.school),
            label: context.t('navPrep'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.trending_up_outlined),
            selectedIcon: const Icon(Icons.trending_up),
            label: context.t('navMarket'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.history_outlined),
            selectedIcon: const Icon(Icons.history),
            label: context.t('navHistory'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.people_outline),
            selectedIcon: const Icon(Icons.people),
            label: context.t('navCommunity'),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    switch (_selectedIndex) {
      case 0:
        return const _PrepTab();
      case 1:
        return const _MarketTab();
      case 2:
        return const _HistoryTab();
      case 3:
        return const _CommunityTab();
      default:
        return const _PrepTab();
    }
  }
}

class _EconomicsStrip extends StatelessWidget {
  const _EconomicsStrip({required this.balance});

  final double balance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.primaryContainer.withValues(alpha: 0.35),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            Icon(Icons.hub, size: 18, color: theme.colorScheme.primary),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'AI Market · hub.aicom.io · channel \$${balance.toStringAsFixed(2)} · TEE verify on',
                style: theme.textTheme.labelLarge,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            TextButton(onPressed: () {}, child: const Text('Add \$5')),
          ],
        ),
      ),
    );
  }
}

class _PrepTab extends StatelessWidget {
  const _PrepTab();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          context.t('todaysPrep'),
          style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        Text(
          'Company-specific banks with freshness signals from the marketplace.',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 20),
        _HeroStatRow(
          stats: const [
            _StatChip(label: 'Readiness', value: '—', icon: Icons.speed),
            _StatChip(label: 'Streak', value: '—', icon: Icons.local_fire_department),
            _StatChip(label: 'Practice avg', value: '—', icon: Icons.star),
          ],
        ),
        const SizedBox(height: 20),
        Card(
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: theme.colorScheme.primaryContainer,
              child: const Icon(Icons.search),
            ),
            title: const Text('Discover Question Banks'),
            subtitle: const Text('Google SWE · Meta PM · Amazon SDE — from \$0.08/call'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () {},
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: theme.colorScheme.secondaryContainer,
              child: const Icon(Icons.record_voice_over),
            ),
            title: const Text('Mock Interview'),
            subtitle: const Text('AI simulation with TEE-verified scoring'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () {},
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: theme.colorScheme.tertiaryContainer,
              child: const Icon(Icons.bolt),
            ),
            title: const Text('What was asked this week'),
            subtitle: const Text('Fresh signals · 14 new reports at Google'),
            trailing: Chip(label: Text('LIVE', style: TextStyle(color: theme.colorScheme.primary))),
            onTap: () {},
          ),
        ),
      ],
    );
  }
}

class _MarketTab extends StatelessWidget {
  const _MarketTab();

  static const _listings = [
    _MarketListing(
      title: 'Google SWE Interview Bank Q2',
      seller: 'Interview Labs',
      price: 0.10,
      trust: 0.94,
      fresh: '2h ago',
    ),
    _MarketListing(
      title: 'Meta Behavioral Patterns 2026',
      seller: 'Prep Collective',
      price: 0.08,
      trust: 0.91,
      fresh: '6h ago',
    ),
    _MarketListing(
      title: 'System Design — Fintech',
      seller: 'ArchPrep',
      price: 0.15,
      trust: 0.88,
      fresh: '1d ago',
    ),
    _MarketListing(
      title: 'Amazon Leadership Principles',
      seller: 'CareerForge',
      price: 0.12,
      trust: 0.90,
      fresh: '3h ago',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Marketplace', style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text(
          'Discover → Channel → Invoke → Settle. Pay per question bank with USDT micro-payments.',
          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        TextField(
          decoration: InputDecoration(
            hintText: 'Intent: "Google SWE behavioral 2026"',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: FilledButton(onPressed: () {}, child: const Text('Discover')),
          ),
        ),
        const SizedBox(height: 16),
        ..._listings.map((l) => _MarketListingCard(listing: l)),
      ],
    );
  }
}

class _MarketListing {
  final String title;
  final String seller;
  final double price;
  final double trust;
  final String fresh;

  const _MarketListing({
    required this.title,
    required this.seller,
    required this.price,
    required this.trust,
    required this.fresh,
  });
}

class _MarketListingCard extends StatelessWidget {
  const _MarketListingCard({required this.listing});

  final _MarketListing listing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(listing.title, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
                ),
                Text('\$${listing.price.toStringAsFixed(2)}/call', style: theme.textTheme.labelLarge?.copyWith(color: theme.colorScheme.primary)),
              ],
            ),
            const SizedBox(height: 6),
            Text('${listing.seller} · trust ${(listing.trust * 100).toStringAsFixed(0)}% · updated ${listing.fresh}',
                style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton(onPressed: () {}, child: const Text('Preview')),
                const SizedBox(width: 8),
                FilledButton(onPressed: () {}, child: const Text('Open channel & invoke')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _HistoryTab extends StatelessWidget {
  const _HistoryTab();

  static const _sessions = [
    _SessionRow(company: 'Google', role: 'SWE L4', score: 4.5, spent: 0.40, date: 'May 19'),
    _SessionRow(company: 'Stripe', role: 'Backend', score: 4.0, spent: 0.25, date: 'May 17'),
    _SessionRow(company: 'Meta', role: 'PM', score: 3.8, spent: 0.32, date: 'May 14'),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Session History', style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text('Bill of Materials and TEE receipts for every invoke.',
            style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        const SizedBox(height: 16),
        ..._sessions.map((s) => Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: CircleAvatar(child: Text(s.company[0])),
                title: Text('${s.company} · ${s.role}'),
                subtitle: Text('${s.date} · spent \$${s.spent.toStringAsFixed(2)} · score ${s.score}/5'),
                trailing: const Icon(Icons.receipt_long),
                onTap: () {},
              ),
            )),
      ],
    );
  }
}

class _SessionRow {
  final String company;
  final String role;
  final double score;
  final double spent;
  final String date;

  const _SessionRow({
    required this.company,
    required this.role,
    required this.score,
    required this.spent,
    required this.date,
  });
}

class _CommunityTab extends StatelessWidget {
  const _CommunityTab();

  static const _contributors = [
    _Contributor(name: 'alex_prep', contributions: 42, earned: 18.40),
    _Contributor(name: 'career_ninja', contributions: 37, earned: 15.20),
    _Contributor(name: 'offer_hunter', contributions: 29, earned: 11.80),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Community Signals', style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text(
          'Sell anonymized trajectories — PII stripped on-device before upload.',
          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        Card(
          color: theme.colorScheme.primaryContainer.withValues(alpha: 0.4),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(Icons.volunteer_activism, color: theme.colorScheme.primary, size: 32),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Share your last mock', style: theme.textTheme.titleMedium),
                      Text('Earn ~\$0.50 per verified trajectory', style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
                FilledButton(onPressed: () {}, child: const Text('Publish')),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Text('Top contributors this week', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        ..._contributors.asMap().entries.map((e) {
          final c = e.value;
          return ListTile(
            leading: CircleAvatar(child: Text('${e.key + 1}')),
            title: Text(c.name),
            subtitle: Text('${c.contributions} trajectories'),
            trailing: Text('+\$${c.earned.toStringAsFixed(2)}', style: TextStyle(color: theme.colorScheme.primary, fontWeight: FontWeight.bold)),
          );
        }),
      ],
    );
  }
}

class _Contributor {
  final String name;
  final int contributions;
  final double earned;

  const _Contributor({required this.name, required this.contributions, required this.earned});
}

class _HeroStatRow extends StatelessWidget {
  const _HeroStatRow({required this.stats});

  final List<_StatChip> stats;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: stats
          .map((s) => Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        children: [
                          Icon(s.icon, size: 20),
                          const SizedBox(height: 4),
                          Text(s.value, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                          Text(s.label, style: Theme.of(context).textTheme.labelSmall),
                        ],
                      ),
                    ),
                  ),
                ),
              ))
          .toList(),
    );
  }
}

class _StatChip {
  final String label;
  final String value;
  final IconData icon;

  const _StatChip({required this.label, required this.value, required this.icon});
}
