import 'package:flutter/material.dart';

class PublisherScreen extends StatelessWidget {
  const PublisherScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Publish & Sell')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text(
            'Sell Your Verified Performance Data',
            style: theme.textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            'Creator metrics sell for \$0.10–\$0.50 per data point when '
            'backed by TEE attestation. Algorithms change fast — your '
            'real-time engagement data is the most valuable signal on the market.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 24),

          // Upload / publish card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.upload_file,
                          size: 32, color: theme.colorScheme.primary),
                      const SizedBox(width: 12),
                      Text('Upload Metrics',
                          style: theme.textTheme.titleMedium),
                    ],
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    decoration: const InputDecoration(
                      labelText: 'Platform',
                      hintText: 'tiktok / youtube / instagram / x',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    maxLines: 5,
                    decoration: const InputDecoration(
                      labelText: 'Metrics JSON',
                      hintText:
                          'Paste your engagement metrics, posting times, '
                          'hook conversion rates...',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    onPressed: null, // requires marketplace connection
                    icon: const Icon(Icons.verified),
                    label: const Text('Submit with TEE Attestation'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Signal marketplace listing
          Text('Your Listed Signals', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          Card(
            child: ListTile(
              leading: const Icon(Icons.sell),
              title: const Text('Cooking niche posting times'),
              subtitle: const Text('Listed 3 days ago | 12 purchases'),
              trailing: const Chip(label: Text('Active')),
            ),
          ),
          Card(
            child: ListTile(
              leading: const Icon(Icons.sell),
              title: const Text('Gaming hook benchmarks'),
              subtitle: const Text('Listed 1 week ago | 8 purchases'),
              trailing: const Chip(label: Text('Active')),
            ),
          ),
        ],
      ),
    );
  }
}
