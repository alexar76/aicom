import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'language_pack_loader.dart';

/// Built-in locales shipped with every AICOM desktop SKU.
enum AicomLocale {
  en('en', 'English'),
  ru('ru', 'Русский'),
  es('es', 'Español');

  const AicomLocale(this.code, this.label);

  final String code;
  final String label;

  Locale get flutterLocale => Locale(code);

  static AicomLocale fromCode(String code) {
    return AicomLocale.values.firstWhere(
      (l) => l.code == code,
      orElse: () => AicomLocale.en,
    );
  }
}

/// Persisted locale + external language pack registry for one app instance.
class AicomLocaleController extends ChangeNotifier {
  AicomLocaleController({
    required this.appId,
    required this.appStrings,
  });

  final String appId;
  final Map<String, Map<String, String>> appStrings;

  static const _prefKey = 'aicom_locale_code';

  AicomLocale _locale = AicomLocale.en;
  String? _externalLocaleCode;
  final Map<String, Map<String, String>> _externalPacks = {};

  AicomLocale get locale => _locale;

  String get activeLocaleCode => _externalLocaleCode ?? _locale.code;

  List<Locale> get supportedLocales {
    final codes = <String>{...AicomLocale.values.map((l) => l.code), ..._externalPacks.keys};
    return codes.map(Locale.new).toList();
  }

  Locale get activeFlutterLocale => Locale(activeLocaleCode);

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString('$_prefKey:$appId');
    if (saved != null) {
      if (AicomLocale.values.any((l) => l.code == saved)) {
        _locale = AicomLocale.fromCode(saved);
        _externalLocaleCode = null;
      } else {
        _externalLocaleCode = saved;
      }
    }
    await reloadExternalPacks();
    notifyListeners();
  }

  Future<void> setLocale(AicomLocale locale) async {
    _locale = locale;
    _externalLocaleCode = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('$_prefKey:$appId', locale.code);
    notifyListeners();
  }

  Future<void> setLocaleCode(String code) async {
    if (_externalPacks.containsKey(code)) {
      _externalLocaleCode = code;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('$_prefKey:$appId', code);
      notifyListeners();
      return;
    }
    await setLocale(AicomLocale.fromCode(code));
  }

  Future<void> reloadExternalPacks() async {
    _externalPacks
      ..clear()
      ..addAll(await LanguagePackLoader.loadForApp(appId));
  }

  String t(String key, {Map<String, String>? params}) {
    final code = activeLocaleCode;
    final value = _externalPacks[code]?[key] ??
        appStrings[code]?[key] ??
        appStrings['en']?[key] ??
        key;
    if (params == null || params.isEmpty) return value;
    var out = value;
    params.forEach((k, v) => out = out.replaceAll('{$k}', v));
    return out;
  }
}
