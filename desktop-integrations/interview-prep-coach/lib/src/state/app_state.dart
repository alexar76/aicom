import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Application state for Interview Prep Coach.
///
/// Manages theme, onboarding, company/role selection, and
/// marketplace interactions.
class AppState extends ChangeNotifier {
  static const _keyOnboardingComplete = 'onboarding_complete';
  static const _keyTargetCompany = 'target_company';
  static const _keyTargetRole = 'target_role';
  static const _keyThemeMode = 'theme_mode';

  bool _onboardingComplete = false;
  String? _targetCompany;
  String? _targetRole;
  ThemeMode _themeMode = ThemeMode.system;
  bool _marketplaceConnected = false;

  bool get onboardingComplete => _onboardingComplete;
  String? get targetCompany => _targetCompany;
  String? get targetRole => _targetRole;
  ThemeMode get themeMode => _themeMode;
  bool get marketplaceConnected => _marketplaceConnected;

  /// Load all persisted state from shared_preferences.
  Future<void> loadPersistedState() async {
    final prefs = await SharedPreferences.getInstance();
    _onboardingComplete = prefs.getBool(_keyOnboardingComplete) ?? false;
    _targetCompany = prefs.getString(_keyTargetCompany);
    _targetRole = prefs.getString(_keyTargetRole);
    final themeStr = prefs.getString(_keyThemeMode);
    _themeMode = _parseThemeMode(themeStr);
    notifyListeners();
  }

  /// Mark onboarding as complete.
  Future<void> completeOnboarding() async {
    _onboardingComplete = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyOnboardingComplete, true);
    notifyListeners();
  }

  /// Set target company and role for interview prep.
  Future<void> setTarget({
    required String company,
    required String role,
  }) async {
    _targetCompany = company;
    _targetRole = role;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyTargetCompany, company);
    await prefs.setString(_keyTargetRole, role);
    notifyListeners();
  }

  /// Set the theme mode.
  Future<void> setThemeMode(ThemeMode mode) async {
    _themeMode = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyThemeMode, mode.name);
    notifyListeners();
  }

  /// Mark marketplace connection status.
  void setMarketplaceConnected(bool connected) {
    _marketplaceConnected = connected;
    notifyListeners();
  }

  ThemeMode _parseThemeMode(String? value) {
    switch (value) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }
}
