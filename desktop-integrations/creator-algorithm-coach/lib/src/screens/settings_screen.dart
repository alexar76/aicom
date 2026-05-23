import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          // Marketplace connection
          Text('Marketplace Connection', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Hub URL', style: theme.textTheme.bodySmall),
                  Text(appState.hubUrl, style: theme.textTheme.bodyMedium),
                  const SizedBox(height: 12),
                  Text('Wallet', style: theme.textTheme.bodySmall),
                  Text(
                    appState.walletAddress ?? 'Not connected',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: appState.walletAddress != null
                          ? Colors.green
                          : Colors.grey,
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (!appState.isMarketplaceConnected)
                    FilledButton.icon(
                      onPressed: () => _connectWallet(context, appState),
                      icon: const Icon(Icons.wallet),
                      label: const Text('Connect Wallet'),
                    )
                  else
                    OutlinedButton.icon(
                      onPressed: () => appState.disconnectMarketplace(),
                      icon: const Icon(Icons.logout),
                      label: const Text('Disconnect'),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Platform preferences
          Text('Platform Preferences', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  CheckboxListTile(
                    title: const Text('TikTok'),
                    value: true,
                    onChanged: (_) {},
                  ),
                  CheckboxListTile(
                    title: const Text('YouTube'),
                    value: true,
                    onChanged: (_) {},
                  ),
                  CheckboxListTile(
                    title: const Text('Instagram'),
                    value: true,
                    onChanged: (_) {},
                  ),
                  CheckboxListTile(
                    title: const Text('X / Twitter'),
                    value: false,
                    onChanged: (_) {},
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Budget
          Text('Weekly Budget', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('\$${appState.budgetUsd.toStringAsFixed(2)} / week'),
                  Slider(
                    value: appState.budgetUsd,
                    min: 1.0,
                    max: 50.0,
                    divisions: 49,
                    label: '\$${appState.budgetUsd.toStringAsFixed(2)}',
                    onChanged: (v) => appState.budgetUsd = v,
                  ),
                  Text(
                    'Tier 3: fastest data decay — recommended \$5–\$20/week for active creators',
                    style: theme.textTheme.bodySmall?.copyWith(color: Colors.grey),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _connectWallet(BuildContext context, AppState appState) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Connect Wallet'),
        content: const Text(
          'Paste your wallet private key to connect to the AI Market.\n\n'
          'Your key stays on-device and is only used to sign marketplace transactions.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              appState.setMarketplaceConnected('0x...connected');
              Navigator.pop(ctx);
            },
            child: const Text('Connect'),
          ),
        ],
      ),
    );
  }
}
