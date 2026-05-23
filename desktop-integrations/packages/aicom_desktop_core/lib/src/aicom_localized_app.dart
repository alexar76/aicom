import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import '../l10n/aicom_core_localizations.dart';
import 'backup/user_data_backup.dart';
import 'locale/aicom_locale_controller.dart';

export 'backup/user_data_backup.dart';
export 'locale/aicom_locale_controller.dart';
export 'locale/language_pack_loader.dart';

/// Extension: `context.t('navDashboard')` using app string catalog.
extension AicomL10nContext on BuildContext {
  String t(String key, {Map<String, String>? params}) {
    return read<AicomLocaleController>().t(key, params: params);
  }

  AicomLocaleController get localeController => read<AicomLocaleController>();
}

/// Bootstraps locale controller and backup hooks for a desktop SKU.
class AicomLocalizedApp extends StatefulWidget {
  const AicomLocalizedApp({
    super.key,
    required this.appId,
    required this.appStrings,
    required this.builder,
    this.collectBackupData,
    this.restoreBackupData,
  });

  final String appId;
  final Map<String, Map<String, String>> appStrings;
  final Widget Function(BuildContext context, AicomLocaleController locale) builder;
  final Future<Map<String, dynamic>> Function()? collectBackupData;
  final Future<void> Function(Map<String, dynamic> data)? restoreBackupData;

  @override
  State<AicomLocalizedApp> createState() => AicomLocalizedAppState();
}

class AicomLocalizedAppState extends State<AicomLocalizedApp> {
  late final AicomLocaleController _locale;
  late final UserDataBackupService _backup;

  @override
  void initState() {
    super.initState();
    _locale = AicomLocaleController(appId: widget.appId, appStrings: widget.appStrings)
      ..load();
    _backup = UserDataBackupService(appId: widget.appId);
  }

  @override
  void dispose() {
    _locale.dispose();
    super.dispose();
  }

  Future<void> exportBackup(BuildContext context) async {
    if (widget.collectBackupData == null) return;
    try {
      final data = await widget.collectBackupData!();
      if (!context.mounted) return;
      await _backup.exportToFile(context: context, payload: data);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.t('backupExported'))),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${context.t('backupFailed')}: $e')),
      );
    }
  }

  Future<void> importBackup(BuildContext context) async {
    if (widget.restoreBackupData == null) return;
    try {
      final data = await _backup.importFromFile();
      if (data == null || !context.mounted) return;
      await widget.restoreBackupData!(data);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.t('backupImported'))),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${context.t('backupFailed')}: $e')),
      );
    }
  }

  void openSettingsSheet(BuildContext context) {
    AicomCoreLocalizations? core;
    try {
      core = AicomCoreLocalizations.of(context);
    } catch (_) {
      core = lookupAicomCoreLocalizations(_locale.activeFlutterLocale);
    }
    final c = core!;

    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(ctx).bottom),
        child: Consumer<AicomLocaleController>(
          builder: (context, locale, _) {
            final builtInActive = AicomLocale.values.any((l) => l.code == locale.activeLocaleCode);
            return ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
              children: [
                Text(context.t('settings'), style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 16),
                Text(c.language, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                ...AicomLocale.values.map(
                  (l) => RadioListTile<AicomLocale>(
                    title: Text(l.label),
                    value: l,
                    groupValue: builtInActive ? AicomLocale.fromCode(locale.activeLocaleCode) : null,
                    onChanged: (_) => locale.setLocale(l),
                  ),
                ),
                if (locale.supportedLocales.length > AicomLocale.values.length) ...[
                  const Divider(),
                  ...locale.supportedLocales
                      .where((l) => !AicomLocale.values.any((b) => b.code == l.languageCode))
                      .map(
                        (l) => ListTile(
                          title: Text('Pack: ${l.languageCode}'),
                          trailing: locale.activeLocaleCode == l.languageCode
                              ? const Icon(Icons.check)
                              : null,
                          onTap: () => locale.setLocaleCode(l.languageCode),
                        ),
                      ),
                ],
                const SizedBox(height: 8),
                Text(
                  c.languagePacksHint(widget.appId),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () async {
                      await locale.reloadExternalPacks();
                      if (ctx.mounted) Navigator.pop(ctx);
                    },
                    icon: const Icon(Icons.refresh),
                    label: Text(c.reloadLanguagePacks),
                  ),
                ),
                const Divider(height: 32),
                Text(context.t('backupTitle'), style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                FilledButton.icon(
                  onPressed: widget.collectBackupData == null ? null : () => exportBackup(context),
                  icon: const Icon(Icons.upload_file),
                  label: Text(context.t('exportBackup')),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: widget.restoreBackupData == null ? null : () => importBackup(context),
                  icon: const Icon(Icons.download),
                  label: Text(context.t('importBackup')),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: _locale,
      child: ListenableBuilder(
        listenable: _locale,
        builder: (context, _) {
          return _SettingsScope(
            openSettings: () => openSettingsSheet(context),
            child: widget.builder(context, _locale),
          );
        },
      ),
    );
  }
}

class _SettingsScope extends InheritedWidget {
  const _SettingsScope({required this.openSettings, required super.child});

  final VoidCallback openSettings;

  static VoidCallback of(BuildContext context) {
    return context.dependOnInheritedWidgetOfExactType<_SettingsScope>()!.openSettings;
  }

  @override
  bool updateShouldNotify(_SettingsScope oldWidget) => false;
}

/// Settings icon for AppBar — opens language + backup sheet.
class AicomSettingsButton extends StatelessWidget {
  const AicomSettingsButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: const Icon(Icons.settings_outlined),
      tooltip: context.t('settings'),
      onPressed: _SettingsScope.of(context),
    );
  }
}

/// MaterialApp helpers — pass to each SKU root widget.
abstract final class AicomLocalization {
  static List<LocalizationsDelegate<dynamic>> get delegates => const [
        AicomCoreLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ];

  static List<Locale> localesFor(AicomLocaleController controller) {
    return controller.supportedLocales;
  }
}
