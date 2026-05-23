import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import 'backup_file_io.dart' if (dart.library.html) 'backup_file_web.dart' as backup_file;

/// Export / import user-owned app data as a versioned JSON backup file.
class UserDataBackupService {
  UserDataBackupService({required this.appId});

  final String appId;

  static const backupVersion = 1;

  Future<void> exportToFile({
    required BuildContext context,
    required Map<String, dynamic> payload,
    String? suggestedName,
  }) async {
    final envelope = {
      'format': 'aicom-user-backup',
      'version': backupVersion,
      'app_id': appId,
      'exported_at': DateTime.now().toUtc().toIso8601String(),
      'data': payload,
    };
    final json = const JsonEncoder.withIndent('  ').convert(envelope);
    final name = suggestedName ?? '$appId-backup-${DateTime.now().millisecondsSinceEpoch}.json';

    if (kIsWeb) {
      await backup_file.exportBackupWeb(context, json);
      return;
    }

    final path = await FilePicker.platform.saveFile(
      dialogTitle: 'Export user data',
      fileName: name,
      type: FileType.custom,
      allowedExtensions: ['json'],
    );
    if (path == null) return;
    await backup_file.writeBackupFile(path, json);
  }

  Future<Map<String, dynamic>?> importFromFile() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['json'],
      withData: kIsWeb,
    );
    if (result == null || result.files.isEmpty) return null;

    final file = result.files.single;
    final raw = kIsWeb
        ? utf8.decode(file.bytes!)
        : await backup_file.readBackupFile(file.path!);

    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    if (decoded['format'] != 'aicom-user-backup') {
      throw FormatException('Not an AICOM backup file');
    }
    if (decoded['app_id'] != appId) {
      throw FormatException('Backup belongs to ${decoded['app_id']}, not $appId');
    }
    return Map<String, dynamic>.from(decoded['data'] as Map);
  }
}
