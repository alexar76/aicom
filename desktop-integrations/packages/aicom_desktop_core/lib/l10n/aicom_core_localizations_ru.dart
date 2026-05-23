// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'aicom_core_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Russian (`ru`).
class AicomCoreLocalizationsRu extends AicomCoreLocalizations {
  AicomCoreLocalizationsRu([String locale = 'ru']) : super(locale);

  @override
  String get connectWallet => 'Подключите кошелёк для AI Market Protocol';

  @override
  String get connect => 'Подключить';

  @override
  String channelBalance(String balance) {
    return 'канал $balance';
  }

  @override
  String sessionSpent(String amount) {
    return 'потрачено $amount';
  }

  @override
  String economicsLine(String hub, String channel, String spent) {
    return '$hub · $channel · $spent';
  }

  @override
  String get settings => 'Настройки';

  @override
  String get language => 'Язык';

  @override
  String get languagePacksTitle => 'Языковые пакеты';

  @override
  String languagePacksHint(Object appId) {
    return 'Положите JSON-пакеты в language-packs/$appId/ (например de.json). Перезапустите или нажмите «Обновить пакеты».';
  }

  @override
  String get reloadLanguagePacks => 'Обновить языковые пакеты';

  @override
  String get backupTitle => 'Резервное копирование';

  @override
  String get exportBackup => 'Экспорт данных в файл';

  @override
  String get importBackup => 'Импорт данных из файла';

  @override
  String get backupExported => 'Резервная копия сохранена';

  @override
  String get backupImported => 'Данные восстановлены';

  @override
  String get backupFailed => 'Ошибка резервного копирования';

  @override
  String get selectLanguage => 'Выберите язык';

  @override
  String get english => 'English';

  @override
  String get russian => 'Русский';

  @override
  String get spanish => 'Español';
}
