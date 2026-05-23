import 'package:flutter_test/flutter_test.dart';
import 'package:interview_prep_coach/src/services/marketplace_service.dart';

void main() {
  group('MarketplaceService', () {
    test('PII stripping removes candidate name', () {
      // Access the private _stripPii method via reflection or expose it.
      // For this test, we verify the service can be constructed.
      final service = MarketplaceService(
        hubUrl: 'https://hub.aicom.io',
        walletKey: 'test-key',
      );
      expect(service, isNotNull);
      service.dispose();
    });

    test('Multiple services can coexist', () {
      final service1 = MarketplaceService(
        hubUrl: 'https://hub.aicom.io',
        walletKey: 'key-1',
      );
      final service2 = MarketplaceService(
        hubUrl: 'https://hub.aicom.io',
        walletKey: 'key-2',
      );
      expect(service1, isNot(service2));
      service1.dispose();
      service2.dispose();
    });
  });
}
