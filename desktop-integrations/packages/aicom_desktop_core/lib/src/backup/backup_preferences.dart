import 'package:shared_preferences/shared_preferences.dart';

/// Collects persisted keys scoped to one desktop SKU for backup export.
Future<Map<String, dynamic>> collectPreferencesBackup(String appId) async {
  final prefs = await SharedPreferences.getInstance();
  final out = <String, dynamic>{};
  for (final key in prefs.getKeys()) {
    if (!key.contains(appId) && !key.startsWith('aicom_')) continue;
    out[key] = prefs.get(key);
  }
  return out;
}

Future<void> restorePreferencesBackup(Map<String, dynamic> data) async {
  final prefs = await SharedPreferences.getInstance();
  for (final entry in data.entries) {
    final v = entry.value;
    if (v is String) {
      await prefs.setString(entry.key, v);
    } else if (v is bool) {
      await prefs.setBool(entry.key, v);
    } else if (v is int) {
      await prefs.setInt(entry.key, v);
    } else if (v is double) {
      await prefs.setDouble(entry.key, v);
    } else if (v is List<String>) {
      await prefs.setStringList(entry.key, v);
    }
  }
}
