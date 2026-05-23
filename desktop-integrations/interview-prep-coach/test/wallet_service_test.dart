import 'package:flutter_test/flutter_test.dart';
import 'package:interview_prep_coach/src/services/wallet_service.dart';

void main() {
  group('WalletService', () {
    test('initial state is uninitialized', () {
      final wallet = WalletService();
      expect(wallet.isInitialized, false);
      expect(wallet.address, isNull);
      expect(wallet.privateKey, isNull);
    });
  });
}
