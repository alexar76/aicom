import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/shell_screen.dart';
import 'screens/wizard/setup_wizard_screen.dart';
import 'state/app_state.dart';
import 'theme/app_theme.dart';

const _skipOnboarding =
    bool.fromEnvironment('SKIP_ONBOARDING', defaultValue: false);

/// Root widget that bootstraps the app, loads persisted state,
/// routes to setup wizard or main shell.
class AppBootstrap extends StatefulWidget {
  const AppBootstrap({super.key});

  @override
  State<AppBootstrap> createState() => _AppBootstrapState();
}

class _AppBootstrapState extends State<AppBootstrap> {
  bool _ready = false;
  String? _initError;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      final appState = context.read<AppState>();
      await appState.loadPersistedState();
      if (!mounted) return;
      setState(() {
        _initError = null;
        _ready = true;
      });
    } catch (e, st) {
      debugPrint('AppBootstrap init failed: $e\n$st');
      if (!mounted) return;
      setState(() {
        _initError = e.toString();
        _ready = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_ready && _initError != null) {
      return MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        themeMode: ThemeMode.system,
        home: Scaffold(
          body: Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: Colors.red),
                  const SizedBox(height: 16),
                  Text(
                    'Failed to start',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _initError!,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: () {
                      setState(() {
                        _ready = false;
                        _initError = null;
                      });
                      _init();
                    },
                    child: const Text('Retry'),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    if (!_ready) {
      return MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        themeMode: ThemeMode.system,
        home: const Scaffold(
          body: Center(child: CircularProgressIndicator()),
        ),
      );
    }

    return Consumer2<AppState, AicomLocaleController>(
      builder: (context, state, locale, _) {
        return MaterialApp(
          title: context.t('appTitle'),
          debugShowCheckedModeBanner: false,
          locale: locale.activeFlutterLocale,
          supportedLocales: AicomLocalization.localesFor(locale),
          localizationsDelegates: AicomLocalization.delegates,
          theme: AppTheme.light,
          darkTheme: AppTheme.dark,
          themeMode: state.themeMode,
          home: (state.onboardingComplete || (_skipOnboarding && kIsWeb))
              ? const ShellScreen()
              : const SetupWizardScreen(),
        );
      },
    );
  }
}
