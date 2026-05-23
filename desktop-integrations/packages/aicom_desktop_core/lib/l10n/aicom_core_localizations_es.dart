// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'aicom_core_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AicomCoreLocalizationsEs extends AicomCoreLocalizations {
  AicomCoreLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get connectWallet =>
      'Conecta la billetera para usar AI Market Protocol';

  @override
  String get connect => 'Conectar';

  @override
  String channelBalance(String balance) {
    return 'canal $balance';
  }

  @override
  String sessionSpent(String amount) {
    return 'gastado $amount';
  }

  @override
  String economicsLine(String hub, String channel, String spent) {
    return '$hub · $channel · $spent';
  }

  @override
  String get settings => 'Ajustes';

  @override
  String get language => 'Idioma';

  @override
  String get languagePacksTitle => 'Paquetes de idioma';

  @override
  String languagePacksHint(Object appId) {
    return 'Coloca paquetes JSON en language-packs/$appId/ (p. ej. de.json). Reinicia o pulsa «Recargar paquetes».';
  }

  @override
  String get reloadLanguagePacks => 'Recargar paquetes de idioma';

  @override
  String get backupTitle => 'Copia de seguridad';

  @override
  String get exportBackup => 'Exportar datos a archivo';

  @override
  String get importBackup => 'Importar datos desde archivo';

  @override
  String get backupExported => 'Copia guardada';

  @override
  String get backupImported => 'Datos restaurados';

  @override
  String get backupFailed => 'Error en la copia de seguridad';

  @override
  String get selectLanguage => 'Seleccionar idioma';

  @override
  String get english => 'English';

  @override
  String get russian => 'Русский';

  @override
  String get spanish => 'Español';
}
