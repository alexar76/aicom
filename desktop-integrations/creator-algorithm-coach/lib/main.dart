import 'package:aicom_desktop_core/aicom_desktop_core.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:aicom_platform_init/aicom_platform_init.dart';
import 'package:provider/provider.dart';

import 'l10n/app_strings.dart';
import 'src/app.dart';
import 'src/services/marketplace_service.dart';
import 'src/state/app_state.dart';

const _appId = 'creator-algorithm-coach';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb) {
    initDatabaseFactory();
  }
  runApp(const CreatorAlgorithmCoachApp());
}

class CreatorAlgorithmCoachApp extends StatelessWidget {
  const CreatorAlgorithmCoachApp({super.key});

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
          Provider(
            create: (_) => MarketplaceService(
              hubUrl: 'https://hub.aicom.io',
            ),
          ),
        ],
        child: const AppBootstrap(),
      ),
    );
  }
}
