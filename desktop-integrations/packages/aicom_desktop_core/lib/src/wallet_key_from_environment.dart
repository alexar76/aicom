/// Resolve wallet key for production builds.
///
/// Set at compile time: `flutter build ... --dart-define=WALLET_KEY=hex...`
/// Returns null when unset — apps must show empty states instead of dev mocks.
String? walletKeyFromEnvironment() {
  const envKey = String.fromEnvironment('WALLET_KEY', defaultValue: '');
  if (envKey.isNotEmpty) return envKey;
  return null;
}
