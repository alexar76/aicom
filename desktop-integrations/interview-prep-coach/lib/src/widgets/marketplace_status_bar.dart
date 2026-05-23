import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/marketplace_service.dart';

/// Displays marketplace connection status and channel balance.
class MarketplaceStatusBar extends StatelessWidget {
  const MarketplaceStatusBar({super.key});

  @override
  Widget build(BuildContext context) {
    // In a real app, this would listen to a MarketplaceState notifier.
    return PopupMenuButton<String>(
      tooltip: 'Marketplace',
      icon: Badge(
        smallSize: 8,
        child: const Icon(Icons.account_balance_wallet_outlined),
      ),
      onSelected: (value) {
        // Handle menu selection.
      },
      itemBuilder: (context) => [
        const PopupMenuItem(
          enabled: false,
          child: Text('Marketplace Wallet'),
        ),
        PopupMenuItem(
          enabled: false,
          child: Row(
            children: [
              const Icon(Icons.circle, size: 8, color: Colors.green),
              const SizedBox(width: 8),
              const Text('Connected'),
              const Spacer(),
              Text(
                '\$${context.read<MarketplaceService>().channelBalance?.toStringAsFixed(2) ?? '0.00'}',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
            ],
          ),
        ),
        const PopupMenuDivider(),
        const PopupMenuItem(
          value: 'deposit',
          child: ListTile(
            leading: Icon(Icons.add_circle_outline),
            title: Text('Add Funds'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
        const PopupMenuItem(
          value: 'transactions',
          child: ListTile(
            leading: Icon(Icons.receipt_long),
            title: Text('Transaction History'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
      ],
    );
  }
}
