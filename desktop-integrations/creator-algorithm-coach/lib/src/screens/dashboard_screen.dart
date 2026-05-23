import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Creator Algorithm Coach')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          // Platform selector row
          Text('Active Platform', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            value: appState.activePlatform,
            decoration: const InputDecoration(border: OutlineInputBorder()),
            items: const [
              DropdownMenuItem(value: 'tiktok', child: Text('TikTok')),
              DropdownMenuItem(value: 'youtube', child: Text('YouTube')),
              DropdownMenuItem(value: 'instagram', child: Text('Instagram')),
              DropdownMenuItem(value: 'x', child: Text('X / Twitter')),
            ],
            onChanged: (v) {
              if (v != null) appState.activePlatform = v;
            },
          ),
          const SizedBox(height: 24),

          // Niche input
          Text('Your Niche', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          TextField(
            decoration: const InputDecoration(
              hintText: 'e.g. cooking, gaming, fintech, fitness',
              border: OutlineInputBorder(),
            ),
            onChanged: (v) => appState.niche = v,
          ),
          const SizedBox(height: 24),

          // Algorithm freshness indicator
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  const Icon(Icons.update, size: 40, color: Colors.green),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Algorithm Signals', style: theme.textTheme.titleSmall),
                        const SizedBox(height: 4),
                        Text(
                          'Tier 3: Weekly updates — fastest decay, ideal for '
                          'short-form creators who need today\'s rules, not last month\'s.',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Recent signals preview
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Recent Signals', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 12),
                  _signalRow('Optimal posting time', '3:14 PM EST', 'TikTok'),
                  _signalRow('Trend window open', 'Recipe videos < 30s', 'TikTok'),
                  _signalRow('Top hook', '\"Stop scrolling if...\"', 'TikTok'),
                  _signalRow('Structure', 'Pattern interrupt + hook', 'TikTok'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Marketplace connection status
          Card(
            color: appState.isMarketplaceConnected
                ? Colors.green.withOpacity(0.1)
                : Colors.orange.withOpacity(0.1),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Icon(
                    appState.isMarketplaceConnected
                        ? Icons.check_circle
                        : Icons.warning_amber,
                    color: appState.isMarketplaceConnected ? Colors.green : Colors.orange,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    appState.isMarketplaceConnected
                        ? 'Marketplace connected'
                        : 'Marketplace not connected',
                    style: theme.textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _signalRow(String label, String value, String platform) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          SizedBox(
            width: 160,
            child: Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
          ),
          Expanded(child: Text(value)),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: Colors.grey.withOpacity(0.15),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(platform, style: const TextStyle(fontSize: 11)),
          ),
        ],
      ),
    );
  }
}
