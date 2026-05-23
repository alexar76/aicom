/// Domain models for algorithm signals.

class AlgorithmSignal {
  final String id;
  final String platform;
  final String niche;
  final String signalType; // optimal_time | trend_window | hook_benchmark | algorithm_shift
  final Map<String, dynamic> data;
  final double confidence;
  final DateTime purchasedAt;
  final double priceUsd;
  final bool teeVerified;
  final String? teeReceiptId;

  const AlgorithmSignal({
    required this.id,
    required this.platform,
    required this.niche,
    required this.signalType,
    required this.data,
    required this.confidence,
    required this.purchasedAt,
    required this.priceUsd,
    required this.teeVerified,
    this.teeReceiptId,
  });
}

class AlgorithmShift {
  final String id;
  final String platform;
  final String description;
  final String impact; // high | medium | low
  final DateTime detectedAt;

  const AlgorithmShift({
    required this.id,
    required this.platform,
    required this.description,
    required this.impact,
    required this.detectedAt,
  });
}

class CreatorMetrics {
  final String platform;
  final String niche;
  final Map<String, dynamic> metrics;
  final DateTime periodStart;
  final DateTime periodEnd;
  final int sampleSize;

  const CreatorMetrics({
    required this.platform,
    required this.niche,
    required this.metrics,
    required this.periodStart,
    required this.periodEnd,
    required this.sampleSize,
  });
}
