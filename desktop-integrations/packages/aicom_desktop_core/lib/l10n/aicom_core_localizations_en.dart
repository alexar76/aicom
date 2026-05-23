// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'aicom_core_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AicomCoreLocalizationsEn extends AicomCoreLocalizations {
  AicomCoreLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get connectWallet => 'Connect wallet to use AI Market Protocol';

  @override
  String get connect => 'Connect';

  @override
  String channelBalance(String balance) {
    return 'channel $balance';
  }

  @override
  String sessionSpent(String amount) {
    return 'spent $amount';
  }

  @override
  String economicsLine(String hub, String channel, String spent) {
    return '$hub · $channel · $spent';
  }

  @override
  String get settings => 'Settings';

  @override
  String get language => 'Language';

  @override
  String get languagePacksTitle => 'Language packs';

  @override
  String languagePacksHint(Object appId) {
    return 'Drop JSON packs into language-packs/$appId/ (e.g. de.json). Restart or tap Reload packs.';
  }

  @override
  String get reloadLanguagePacks => 'Reload language packs';

  @override
  String get backupTitle => 'Backup & restore';

  @override
  String get exportBackup => 'Export user data to file';

  @override
  String get importBackup => 'Import user data from file';

  @override
  String get backupExported => 'Backup saved';

  @override
  String get backupImported => 'Backup restored';

  @override
  String get backupFailed => 'Backup operation failed';

  @override
  String get selectLanguage => 'Select language';

  @override
  String get english => 'English';

  @override
  String get russian => 'Russian';

  @override
  String get spanish => 'Spanish';
}
