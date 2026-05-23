import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path_provider/path_provider.dart';

/// Loads optional JSON language packs from disk.
///
/// Search order:
/// 1. `{appDocuments}/AICOM/language-packs/{appId}/*.json`
/// 2. `{cwd}/language-packs/{appId}/*.json` (dev / CI)
class LanguagePackLoader {
  LanguagePackLoader._();

  static Future<Map<String, Map<String, String>>> loadForApp(String appId) async {
    if (kIsWeb) {
      return {};
    }

    final packs = <String, Map<String, String>>{};
    final dirs = await _candidateDirs(appId);
    for (final dir in dirs) {
      if (!await dir.exists()) continue;
      await for (final entity in dir.list()) {
        if (entity is! File || !entity.path.endsWith('.json')) continue;
        try {
          final raw = await entity.readAsString();
          final decoded = jsonDecode(raw) as Map<String, dynamic>;
          final locale = (decoded['@@locale'] as String?) ??
              entity.uri.pathSegments.last.replaceAll('.json', '');
          final strings = <String, String>{};
          decoded.forEach((key, value) {
            if (key.startsWith('@@') || value is! String) return;
            strings[key] = value;
          });
          if (strings.isNotEmpty) {
            packs[locale] = strings;
          }
        } catch (_) {
          // Skip malformed packs — built-in locales remain available.
        }
      }
    }
    return packs;
  }

  static Future<List<Directory>> _candidateDirs(String appId) async {
    final dirs = <Directory>[];
    try {
      final docs = await getApplicationDocumentsDirectory();
      dirs.add(Directory('${docs.path}/AICOM/language-packs/$appId'));
    } catch (_) {}
    dirs.add(Directory('language-packs/$appId'));
    return dirs;
  }
}

/// Example external pack (`language-packs/reputation-dashboard/de.json`):
/// ```json
/// {
///   "@@locale": "de",
///   "appTitle": "Reputation Dashboard",
///   "navTop": "Top-Fähigkeiten"
/// }
/// ```
