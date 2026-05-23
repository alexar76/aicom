import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'state/app_state.dart';
import 'screens/dashboard_screen.dart';
import 'screens/discover_screen.dart';
import 'screens/publisher_screen.dart';
import 'screens/insights_screen.dart';
import 'screens/settings_screen.dart';

class AppBootstrap extends StatelessWidget {
  const AppBootstrap({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AicomLocaleController>(
      builder: (context, locale, _) {
        return MaterialApp(
          title: context.t('appTitle'),
          debugShowCheckedModeBanner: false,
          locale: locale.activeFlutterLocale,
          supportedLocales: AicomLocalization.localesFor(locale),
          localizationsDelegates: AicomLocalization.delegates,
          theme: AicomDesktopTheme.light(seed: AicomProductColors.creatorAlgorithm),
          darkTheme: AicomDesktopTheme.dark(seed: AicomProductColors.creatorAlgorithm),
          themeMode: ThemeMode.system,
          home: const MainShell(),
        );
      },
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _selectedIndex = 0;
  final _walletKey = walletKeyFromEnvironment();
  late final HubSession _hub;

  static const List<Widget> _screens = [
    DashboardScreen(),
    DiscoverScreen(),
    PublisherScreen(),
    InsightsScreen(),
    SettingsScreen(),
  ];

  void _onItemTapped(int index) {
    setState(() => _selectedIndex = index);
  }

  @override
  void initState() {
    super.initState();
    _hub = HubSession(affiliate: 'creator-algorithm-coach', walletKey: _walletKey);
    if (_walletKey != null) _hub.connect();
  }

  @override
  void dispose() {
    _hub.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          MarketplaceEconomicsBar(
            hubLabel: _hub.isConnected ? _hub.hubUrl : 'Hub offline',
            walletConfigured: _walletKey != null,
            channelBalanceUsd: _hub.channelBalanceUsd,
            sessionSpendUsd: _hub.sessionSpendUsd,
          ),
          Expanded(
            child: Row(
              children: [
                NavigationRail(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: _onItemTapped,
                  labelType: NavigationRailLabelType.all,
                  destinations: [
                    NavigationRailDestination(
                      icon: const Icon(Icons.dashboard_outlined),
                      selectedIcon: const Icon(Icons.dashboard),
                      label: Text(context.t('navDashboard')),
                    ),
                    NavigationRailDestination(
                      icon: const Icon(Icons.explore_outlined),
                      selectedIcon: const Icon(Icons.explore),
                      label: Text(context.t('navDiscover')),
                    ),
                    NavigationRailDestination(
                      icon: const Icon(Icons.publish_outlined),
                      selectedIcon: const Icon(Icons.publish),
                      label: Text(context.t('navPublish')),
                    ),
                    NavigationRailDestination(
                      icon: const Icon(Icons.insights_outlined),
                      selectedIcon: const Icon(Icons.insights),
                      label: Text(context.t('navInsights')),
                    ),
                    NavigationRailDestination(
                      icon: const Icon(Icons.settings_outlined),
                      selectedIcon: const Icon(Icons.settings),
                      label: Text(context.t('navSettings')),
                    ),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(child: _screens[_selectedIndex]),
                const Padding(
                  padding: EdgeInsets.only(right: 8),
                  child: AicomSettingsButton(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
