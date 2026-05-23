import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'aicom_core_localizations_en.dart';
import 'aicom_core_localizations_es.dart';
import 'aicom_core_localizations_ru.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AicomCoreLocalizations
/// returned by `AicomCoreLocalizations.of(context)`.
///
/// Applications need to include `AicomCoreLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/aicom_core_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AicomCoreLocalizations.localizationsDelegates,
///   supportedLocales: AicomCoreLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AicomCoreLocalizations.supportedLocales
/// property.
abstract class AicomCoreLocalizations {
  AicomCoreLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AicomCoreLocalizations of(BuildContext context) {
    return Localizations.of<AicomCoreLocalizations>(
        context, AicomCoreLocalizations)!;
  }

  static const LocalizationsDelegate<AicomCoreLocalizations> delegate =
      _AicomCoreLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('es'),
    Locale('ru')
  ];

  /// No description provided for @connectWallet.
  ///
  /// In en, this message translates to:
  /// **'Connect wallet to use AI Market Protocol'**
  String get connectWallet;

  /// No description provided for @connect.
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get connect;

  /// No description provided for @channelBalance.
  ///
  /// In en, this message translates to:
  /// **'channel {balance}'**
  String channelBalance(String balance);

  /// No description provided for @sessionSpent.
  ///
  /// In en, this message translates to:
  /// **'spent {amount}'**
  String sessionSpent(String amount);

  /// No description provided for @economicsLine.
  ///
  /// In en, this message translates to:
  /// **'{hub} · {channel} · {spent}'**
  String economicsLine(String hub, String channel, String spent);

  /// No description provided for @settings.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settings;

  /// No description provided for @language.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get language;

  /// No description provided for @languagePacksTitle.
  ///
  /// In en, this message translates to:
  /// **'Language packs'**
  String get languagePacksTitle;

  /// No description provided for @languagePacksHint.
  ///
  /// In en, this message translates to:
  /// **'Drop JSON packs into language-packs/{appId}/ (e.g. de.json). Restart or tap Reload packs.'**
  String languagePacksHint(Object appId);

  /// No description provided for @reloadLanguagePacks.
  ///
  /// In en, this message translates to:
  /// **'Reload language packs'**
  String get reloadLanguagePacks;

  /// No description provided for @backupTitle.
  ///
  /// In en, this message translates to:
  /// **'Backup & restore'**
  String get backupTitle;

  /// No description provided for @exportBackup.
  ///
  /// In en, this message translates to:
  /// **'Export user data to file'**
  String get exportBackup;

  /// No description provided for @importBackup.
  ///
  /// In en, this message translates to:
  /// **'Import user data from file'**
  String get importBackup;

  /// No description provided for @backupExported.
  ///
  /// In en, this message translates to:
  /// **'Backup saved'**
  String get backupExported;

  /// No description provided for @backupImported.
  ///
  /// In en, this message translates to:
  /// **'Backup restored'**
  String get backupImported;

  /// No description provided for @backupFailed.
  ///
  /// In en, this message translates to:
  /// **'Backup operation failed'**
  String get backupFailed;

  /// No description provided for @selectLanguage.
  ///
  /// In en, this message translates to:
  /// **'Select language'**
  String get selectLanguage;

  /// No description provided for @english.
  ///
  /// In en, this message translates to:
  /// **'English'**
  String get english;

  /// No description provided for @russian.
  ///
  /// In en, this message translates to:
  /// **'Russian'**
  String get russian;

  /// No description provided for @spanish.
  ///
  /// In en, this message translates to:
  /// **'Spanish'**
  String get spanish;
}

class _AicomCoreLocalizationsDelegate
    extends LocalizationsDelegate<AicomCoreLocalizations> {
  const _AicomCoreLocalizationsDelegate();

  @override
  Future<AicomCoreLocalizations> load(Locale locale) {
    return SynchronousFuture<AicomCoreLocalizations>(
        lookupAicomCoreLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'es', 'ru'].contains(locale.languageCode);

  @override
  bool shouldReload(_AicomCoreLocalizationsDelegate old) => false;
}

AicomCoreLocalizations lookupAicomCoreLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AicomCoreLocalizationsEn();
    case 'es':
      return AicomCoreLocalizationsEs();
    case 'ru':
      return AicomCoreLocalizationsRu();
  }

  throw FlutterError(
      'AicomCoreLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
