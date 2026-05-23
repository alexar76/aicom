import 'package:flutter/material.dart';

class SignalCard extends StatelessWidget {
  final String platform;
  final String signalType;
  final String value;
  final double confidence;
  final double price;
  final bool teeVerified;
  final VoidCallback? onBuy;

  const SignalCard({
    super.key,
    required this.platform,
    required this.signalType,
    required this.value,
    required this.confidence,
    required this.price,
    this.teeVerified = false,
    this.onBuy,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(platform, style: const TextStyle(fontSize: 11)),
                ),
                const SizedBox(width: 8),
                if (teeVerified)
                  Icon(Icons.verified, size: 16, color: Colors.green.shade600),
                const Spacer(),
                Text('\$${price.toStringAsFixed(2)}',
                    style: theme.textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: 8),
            Text(signalType, style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(value, style: theme.textTheme.bodyMedium),
            const SizedBox(height: 8),
            Row(
              children: [
                Text('${(confidence * 100).toStringAsFixed(0)}% confidence',
                    style: theme.textTheme.bodySmall?.copyWith(color: Colors.grey)),
                const Spacer(),
                if (onBuy != null)
                  FilledButton.tonal(
                    onPressed: onBuy,
                    child: const Text('Buy'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
