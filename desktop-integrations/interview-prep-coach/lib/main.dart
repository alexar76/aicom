import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:aicom_platform_init/aicom_platform_init.dart';

import 'l10n/app_strings.dart';
import 'src/app.dart';
import 'src/services/marketplace_service.dart';
import 'src/services/wallet_service.dart';
import 'src/state/app_state.dart';

const _appId = 'interview-prep-coach';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb) {
    initDatabaseFactory();
  }
  final wallet = WalletService();
  await wallet.initialize();
  runApp(InterviewPrepCoachApp(wallet: wallet));
}

class InterviewPrepCoachApp extends StatelessWidget {
  const InterviewPrepCoachApp({super.key, required this.wallet});

  final WalletService wallet;

  @override
  Widget build(BuildContext context) {
    return AicomLocalizedApp(
      appId: _appId,
      appStrings: AppStrings.catalog,
      collectBackupData: () async => {
        'preferences': await collectPreferencesBackup(_appId),
      },
      restoreBackupData: (data) async {
        final prefs = data['preferences'];
        if (prefs is Map) await restorePreferencesBackup(Map<String, dynamic>.from(prefs));
      },
      builder: (context, locale) => MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppState()),
          Provider.value(value: wallet),
          Provider(
            create: (_) => MarketplaceService(
              hubUrl: 'https://hub.aicom.io',
              walletKey: wallet.privateKey,
            ),
          ),
        ],
        child: const AppBootstrap(),
      ),
    );
  }
}
