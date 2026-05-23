import 'package:flutter_test/flutter_test.dart';
import 'package:interview_prep_coach/src/models/interview_question.dart';

void main() {
  group('InterviewQuestion', () {
    test('parses from JSON', () {
      final json = {
        'id': 'q-001',
        'question': 'Tell me about a time you led a cross-functional project',
        'category': 'behavioral',
        'difficulty': 'medium',
        'company': 'Google',
        'role': 'Software Engineer',
        'tags': ['leadership', 'cross-functional'],
        'suggested_answer': 'Use STAR method...',
        'key_points': ['Describe the situation', 'Explain your role'],
        'source': 'question_bank',
        'reported_at': '2026-05-20T10:00:00Z',
      };

      final q = InterviewQuestion.fromJson(json);
      expect(q.id, 'q-001');
      expect(q.company, 'Google');
      expect(q.role, 'Software Engineer');
      expect(q.category, 'behavioral');
      expect(q.difficulty, 'medium');
      expect(q.tags, ['leadership', 'cross-functional']);
    });

    test('handles minimal JSON', () {
      final q = InterviewQuestion.fromJson({
        'id': 'q-002',
        'question': 'What is your greatest strength?',
        'category': 'behavioral',
        'difficulty': 'easy',
        'company': 'Meta',
        'reported_at': '2026-05-21T00:00:00Z',
      });

      expect(q.id, 'q-002');
      expect(q.role, isNull);
      expect(q.suggestedAnswer, isNull);
    });

    test('serializes to JSON', () {
      final q = InterviewQuestion(
        id: 'q-003',
        question: 'Design a URL shortening service',
        category: 'system-design',
        difficulty: 'hard',
        company: 'Google',
        role: 'Senior Software Engineer',
        tags: ['scalability', 'distributed-systems'],
        source: 'ai_generated',
        reportedAt: DateTime(2026, 5, 22),
      );

      final json = q.toJson();
      expect(json['id'], 'q-003');
      expect(json['question'], 'Design a URL shortening service');
      expect(json['tags'], ['scalability', 'distributed-systems']);
    });
  });

  group('QuestionBank', () {
    test('parses from JSON', () {
      final json = {
        'id': 'google-swe-q3-2026',
        'product_id': 'google-swe-q3-2026',
        'name': 'Google SWE Q3 2026 Question Bank',
        'company': 'Google',
        'role': 'Software Engineer',
        'description': 'Up-to-date behavioral questions for Google SWE',
        'question_count': 50,
        'price_usd': 0.10,
        'trust_score': 0.95,
        'updated_at': '2026-05-15T00:00:00Z',
        'tags': ['behavioral', 'google', 'swe'],
      };

      final bank = QuestionBank.fromJson(json);
      expect(bank.id, 'google-swe-q3-2026');
      expect(bank.questionCount, 50);
      expect(bank.priceUsd, 0.10);
      expect(bank.trustScore, 0.95);
    });
  });

  group('InterviewTrajectory', () {
    test('toMarketplacePayload strips PII', () {
      final trajectory = InterviewTrajectory(
        question: 'Tell me about a time you had conflict',
        answerSummary: 'I mediated a disagreement between engineers',
        outcome: 'offer',
        company: 'Google',
        role: 'Software Engineer',
        difficulty: 'medium',
        tags: ['conflict-resolution'],
        interviewDate: DateTime(2026, 5, 20),
      );

      final payload = trajectory.toMarketplacePayload();
      expect(payload['question'], isNotNull);
      expect(payload['answer_summary'], isNotNull);
      expect(payload['outcome'], 'offer');
      expect(payload['interview_week'], '2026-W21');
      // Company is not in the marketplace payload (PII stripped)
      expect(payload.containsKey('company'), false);
    });
  });
}
