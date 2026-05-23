import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

class DiscoverScreen extends StatelessWidget {
  const DiscoverScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Discover Algorithm Signals')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            'Marketplace Capabilities',
            style: theme.textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            'Buy weekly-updated algorithm signals by platform. '
            'Every data point is TEE-proven — metrics cannot be faked.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 24),

          // Available signal packs
          _capabilityCard(
            context,
            icon: Icons.access_time,
            title: 'Optimal Posting Times',
            provider: 'TikTok Analysts',
            price: '\$0.15/call',
            description:
                'Per-niche posting time optimization. Updated weekly with '
                'engagement curve data from 10k+ creators.',
          ),
          const SizedBox(height: 12),

          _capabilityCard(
            context,
            icon: Icons.trending_up,
            title: 'Trend Windows',
            provider: 'TrendWatchers DAO',
            price: '\$0.25/call',
            description:
                'Real-time trend window detection. Know which formats, '
                'sounds, and structures are rising before saturation.',
          ),
          const SizedBox(height: 12),

          _capabilityCard(
            context,
            icon: Icons.auto_awesome,
            title: 'Hook & Structure Benchmarks',
            provider: 'CreatorDAO',
            price: '\$0.20/call',
            description:
                'TEE-proven hook conversion rates. See which opening '
                'patterns drive retention in your niche this week.',
          ),
          const SizedBox(height: 12),

          _capabilityCard(
            context,
            icon: Icons.compare_arrows,
            title: 'Algorithm Shift Detector',
            provider: 'Platform Signals Inc.',
            price: '\$0.30/call',
            description:
                'Detect algorithm changes in days, not weeks. '
                'Get notified when ranking signals shift.',
          ),
          const SizedBox(height: 24),

          // Buy signals button
          FilledButton.icon(
            onPressed: appState.isMarketplaceConnected ? () {} : null,
            icon: const Icon(Icons.shopping_cart),
            label: const Text('Buy Algorithm Signals'),
          ),
          if (!appState.isMarketplaceConnected)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                'Connect wallet in Settings to purchase signals.',
                style: theme.textTheme.bodySmall?.copyWith(color: Colors.grey),
              ),
            ),
        ],
      ),
    );
  }

  Widget _capabilityCard(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String provider,
    required String price,
    required String description,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 36, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.primaryContainer,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(price, style: const TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'by $provider',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.grey,
                        ),
                  ),
                  const SizedBox(height: 6),
                  Text(description, style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
