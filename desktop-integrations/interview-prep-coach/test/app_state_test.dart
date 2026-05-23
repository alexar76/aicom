import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:interview_prep_coach/src/state/app_state.dart';

void main() {
  group('AppState', () {
    test('initial state is default', () {
      final state = AppState();
      expect(state.onboardingComplete, false);
      expect(state.targetCompany, isNull);
      expect(state.targetRole, isNull);
      expect(state.themeMode, ThemeMode.system);
      expect(state.marketplaceConnected, false);
    });

    test('setMarketplaceConnected updates state', () {
      final state = AppState();
      var notified = false;
      state.addListener(() => notified = true);

      state.setMarketplaceConnected(true);
      expect(state.marketplaceConnected, true);
      expect(notified, true);
    });

    test('setThemeMode updates state', () async {
      final state = AppState();
      state.addListener(() {}); // prevent unhandled listener errors

      await state.setThemeMode(ThemeMode.dark);
      expect(state.themeMode, ThemeMode.dark);

      await state.setThemeMode(ThemeMode.light);
      expect(state.themeMode, ThemeMode.light);
    });
  });
}
