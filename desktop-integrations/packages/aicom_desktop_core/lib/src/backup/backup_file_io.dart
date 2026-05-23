import 'dart:io';

Future<void> writeBackupFile(String path, String content) async {
  await File(path).writeAsString(content);
}

Future<String> readBackupFile(String path) async {
  return File(path).readAsString();
}

Future<void> exportBackupWeb(Object context, String json) async {
  throw UnsupportedError('Web export uses backup_file_web.dart');
}
