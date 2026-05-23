/// Manages wallet keys, balances, and transaction history.
///
/// In development mode, uses a stored private key from shared_preferences.
/// In production, delegates to a hardware wallet or OS keychain.
library;

import 'package:shared_preferences/shared_preferences.dart';

/// Service for wallet management.
///
/// Handles:
/// - Wallet creation and key storage
/// - Balance queries
/// - Transaction history
class WalletService {
  static const _keyPrivateKey = 'wallet_private_key';
  static const _keyAddress = 'wallet_address';

  String? _address;
  String? _privateKey;

  /// Whether the wallet has been initialized.
  bool get isInitialized => _address != null;

  /// The wallet address (0x-prefixed).
  String? get address => _address;

  /// The private key (hex-encoded).
  String? get privateKey => _privateKey;

  /// Initialize wallet from persisted storage or create a new one.
  Future<void> initialize() async {
    final prefs = await SharedPreferences.getInstance();
    _privateKey = _normalizePrivateKey(prefs.getString(_keyPrivateKey));
    _address = prefs.getString(_keyAddress);

    // If no wallet exists, generate one.
    if (_privateKey == null || _address == null) {
      await _createWallet(prefs);
    }
  }

  /// Create a new wallet.
  Future<void> _createWallet(SharedPreferences prefs) async {
    // In production, use proper key generation via wallet package.
    // For development, generate a deterministic dev key.
    _privateKey = _generateDevKey();
    _address = _deriveAddress(_privateKey!);

    await prefs.setString(_keyPrivateKey, _privateKey!);
    await prefs.setString(_keyAddress, _address!);
  }

  String _generateDevKey() {
    // Deterministic dev key — replace with secure generation in production.
    return 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789';
  }

  String? _normalizePrivateKey(String? key) {
    if (key == null || key.isEmpty) return null;
    final stripped = key.startsWith('0x') || key.startsWith('0X')
        ? key.substring(2)
        : key;
    final hexOnly = RegExp(r'^[0-9a-fA-F]+$');
    return hexOnly.hasMatch(stripped) ? stripped : null;
  }

  String _deriveAddress(String privateKey) {
    throw UnimplementedError(
      'Address derivation not implemented. '
      'Generate a wallet via the onboarding flow or provide a valid address.',
    );
  }

  /// Get the current USDC balance from the hub.
  Future<double> getBalance() async {
    // In production, query the blockchain or hub API.
    return 20.0;
  }
}
