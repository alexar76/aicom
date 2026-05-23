/// Data models for interview questions, question banks, and trajectories.
library;

/// A single interview question with context.
class InterviewQuestion {
  final String id;
  final String question;
  final String category; // behavioral, technical, system-design
  final String? subcategory;
  final String difficulty; // easy, medium, hard
  final String company;
  final String? role;
  final List<String> tags;
  final String? suggestedAnswer;
  final List<String> keyPoints;
  final String source; // question_bank, community, ai_generated
  final DateTime reportedAt;

  const InterviewQuestion({
    required this.id,
    required this.question,
    required this.category,
    this.subcategory,
    required this.difficulty,
    required this.company,
    this.role,
    this.tags = const [],
    this.suggestedAnswer,
    this.keyPoints = const [],
    this.source = 'question_bank',
    required this.reportedAt,
  });

  factory InterviewQuestion.fromJson(Map<String, dynamic> json) {
    return InterviewQuestion(
      id: json['id'] as String? ?? '',
      question: json['question'] as String? ?? '',
      category: json['category'] as String? ?? 'behavioral',
      subcategory: json['subcategory'] as String?,
      difficulty: json['difficulty'] as String? ?? 'medium',
      company: json['company'] as String? ?? '',
      role: json['role'] as String?,
      tags: (json['tags'] as List<dynamic>?)?.cast<String>() ?? [],
      suggestedAnswer: json['suggested_answer'] as String?,
      keyPoints: (json['key_points'] as List<dynamic>?)?.cast<String>() ?? [],
      source: json['source'] as String? ?? 'question_bank',
      reportedAt: DateTime.tryParse(json['reported_at'] as String? ?? '') ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'question': question,
        'category': category,
        'subcategory': subcategory,
        'difficulty': difficulty,
        'company': company,
        'role': role,
        'tags': tags,
        'suggested_answer': suggestedAnswer,
        'key_points': keyPoints,
        'source': source,
        'reported_at': reportedAt.toIso8601String(),
      };
}

/// A question bank product from the marketplace.
class QuestionBank {
  final String id;
  final String productId;
  final String name;
  final String company;
  final String? role;
  final String description;
  final int questionCount;
  final double priceUsd;
  final double? trustScore;
  final DateTime updatedAt;
  final List<String> tags;

  const QuestionBank({
    required this.id,
    required this.productId,
    required this.name,
    required this.company,
    this.role,
    required this.description,
    required this.questionCount,
    required this.priceUsd,
    this.trustScore,
    required this.updatedAt,
    this.tags = const [],
  });

  factory QuestionBank.fromJson(Map<String, dynamic> json) {
    return QuestionBank(
      id: json['id'] as String? ?? '',
      productId: json['product_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      company: json['company'] as String? ?? '',
      role: json['role'] as String?,
      description: json['description'] as String? ?? '',
      questionCount: json['question_count'] as int? ?? 0,
      priceUsd: (json['price_usd'] as num?)?.toDouble() ?? 0.10,
      trustScore: (json['trust_score'] as num?)?.toDouble(),
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ??
          DateTime.now(),
      tags: (json['tags'] as List<dynamic>?)?.cast<String>() ?? [],
    );
  }
}

/// An anonymized interview trajectory for selling on the marketplace.
class InterviewTrajectory {
  final String question;
  final String answerSummary;
  final String outcome; // offer, rejection, in_progress
  final String company;
  final String? role;
  final String difficulty;
  final List<String> tags;
  final DateTime interviewDate;

  const InterviewTrajectory({
    required this.question,
    required this.answerSummary,
    required this.outcome,
    required this.company,
    this.role,
    this.difficulty = 'medium',
    this.tags = const [],
    required this.interviewDate,
  });

  /// Prepare the trajectory for marketplace submission (PII stripped).
  Map<String, dynamic> toMarketplacePayload() => {
        'question': question,
        'answer_summary': answerSummary,
        'outcome': outcome,
        'difficulty': difficulty,
        'tags': tags,
        'interview_week': '${interviewDate.year}-W${_isoWeek(interviewDate)}',
      };

  static int _isoWeek(DateTime date) {
    final dayOfYear = date.difference(DateTime(date.year, 1, 1)).inDays;
    return ((dayOfYear - date.weekday + 10) / 7).floor();
  }
}
