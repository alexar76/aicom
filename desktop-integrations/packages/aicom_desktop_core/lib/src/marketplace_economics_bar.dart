import 'package:flutter/material.dart';

import '../l10n/aicom_core_localizations.dart';

/// Compact strip showing wallet / channel / session spend — AI Market economics.
class MarketplaceEconomicsBar extends StatelessWidget {
  const MarketplaceEconomicsBar({
    super.key,
    required this.hubLabel,
    required this.walletConfigured,
    this.channelBalanceUsd,
    this.sessionSpendUsd = 0,
    this.onConnect,
  });

  final String hubLabel;
  final bool walletConfigured;
  final double? channelBalanceUsd;
  final double sessionSpendUsd;
  final VoidCallback? onConnect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final core = AicomCoreLocalizations.of(context);
    final channel = core.channelBalance('\$${(channelBalanceUsd ?? 0).toStringAsFixed(2)}');
    final spent = core.sessionSpent('\$${sessionSpendUsd.toStringAsFixed(2)}');

    return Material(
      color: theme.colorScheme.surfaceContainerHigh,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          children: [
            Icon(
              walletConfigured ? Icons.account_balance_wallet : Icons.link_off,
              size: 18,
              color: walletConfigured ? theme.colorScheme.primary : theme.colorScheme.error,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                walletConfigured
                    ? core.economicsLine(hubLabel, channel, spent)
                    : core.connectWallet,
                style: theme.textTheme.labelMedium,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (!walletConfigured && onConnect != null)
              TextButton(onPressed: onConnect, child: Text(core.connect)),
          ],
        ),
      ),
    );
  }
}
