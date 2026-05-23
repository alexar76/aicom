import 'package:flutter/material.dart';

/// Polished Material 3 light/dark themes for AICOM desktop products.
class AicomDesktopTheme {
  AicomDesktopTheme._();

  static ThemeData light({
    required Color seed,
    Color scaffold = const Color(0xFFF4F6FA),
  }) {
    final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: Brightness.light);
    return _base(scheme, scaffold: scaffold);
  }

  static ThemeData dark({
    required Color seed,
    Color scaffold = const Color(0xFF0F1117),
  }) {
    final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: Brightness.dark);
    return _base(scheme, scaffold: scaffold);
  }

  static ThemeData _base(ColorScheme scheme, {required Color scaffold}) {
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: scaffold,
      appBarTheme: AppBarTheme(
        centerTitle: false,
        elevation: 0,
        scrolledUnderElevation: 1,
        backgroundColor: scaffold,
        foregroundColor: scheme.onSurface,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surfaceContainerLow,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, 44),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        elevation: 0,
        height: 72,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        indicatorShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      navigationRailTheme: NavigationRailThemeData(
        labelType: NavigationRailLabelType.all,
        groupAlignment: 0,
        indicatorShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant.withValues(alpha: 0.5)),
    );
  }
}

/// Brand seeds per desktop SKU.
abstract final class AicomProductColors {
  static const interviewPrep = Color(0xFF1A73E8);
  static const personalFinance = Color(0xFF00897B);
  static const capabilityComposer = Color(0xFF00D4AA);
  static const coldOutreach = Color(0xFF1565C0);
  static const creatorAlgorithm = Color(0xFF6C3FC5);
  static const discoveryProspector = Color(0xFF1A73E8);
  static const freelanceContract = Color(0xFF1565C0);
  static const reputation = Color(0xFF22C55E);
}
