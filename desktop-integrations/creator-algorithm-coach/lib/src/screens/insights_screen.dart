import 'package:flutter/material.dart';

class InsightsScreen extends StatelessWidget {
  const InsightsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Insights & History')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Text('Algorithm Shift Timeline', style: theme.textTheme.titleLarge),
          const SizedBox(height: 8),
          Text(
            'Tracks algorithm changes across platforms. '
            'The gap between "algorithm changed" and "I noticed" is where revenue is lost.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 24),

          // Timeline
          _timelineEntry(
            context,
            date: '2026-05-20',
            platform: 'TikTok',
            change: 'Favorability score weighting shifted: saves > shares now 2x value',
            impact: 'High',
          ),
          const SizedBox(height: 12),
          _timelineEntry(
            context,
            date: '2026-05-18',
            platform: 'Instagram',
            change: 'Reels < 15s deprioritized in explore feed',
            impact: 'Medium',
          ),
          const SizedBox(height: 12),
          _timelineEntry(
            context,
            date: '2026-05-15',
            platform: 'YouTube',
            change: 'Shorts CTR now weighted above watch time for initial push',
            impact: 'High',
          ),
          const SizedBox(height: 12),
          _timelineEntry(
            context,
            date: '2026-05-12',
            platform: 'X',
            change: 'Reply-to-impression ratio added as ranking signal for trending topics',
            impact: 'Medium',
          ),

          const SizedBox(height: 32),
          Text('Your Signal Purchase History', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          Card(
            child: ListTile(
              leading: const Icon(Icons.receipt_long),
              title: const Text('TikTok cooking optimal times'),
              subtitle: const Text('Purchased May 20 | \$0.15 | TEE verified'),
              trailing: Icon(Icons.check_circle, color: Colors.green.shade600),
            ),
          ),
          Card(
            child: ListTile(
              leading: const Icon(Icons.receipt_long),
              title: const Text('YouTube hook benchmarks'),
              subtitle: const Text('Purchased May 18 | \$0.20 | TEE verified'),
              trailing: Icon(Icons.check_circle, color: Colors.green.shade600),
            ),
          ),
        ],
      ),
    );
  }

  Widget _timelineEntry(
    BuildContext context, {
    required String date,
    required String platform,
    required String change,
    required String impact,
  }) {
    final theme = Theme.of(context);
    final impactColor = impact == 'High' ? Colors.red : Colors.orange;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Column(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: impactColor,
                    shape: BoxShape.circle,
                  ),
                ),
                Container(
                  width: 2,
                  height: 40,
                  color: Colors.grey.withOpacity(0.3),
                ),
              ],
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(date, style: theme.textTheme.bodySmall?.copyWith(
                        color: Colors.grey,
                      )),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                        decoration: BoxDecoration(
                          color: impactColor.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          '$platform · $impact impact',
                          style: TextStyle(fontSize: 11, color: impactColor),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(change, style: theme.textTheme.bodySmall),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
