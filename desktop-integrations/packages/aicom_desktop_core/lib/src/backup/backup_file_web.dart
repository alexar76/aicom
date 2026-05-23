import 'package:flutter/material.dart';

Future<void> writeBackupFile(String path, String content) async {
  throw UnsupportedError('Not available on web');
}

Future<String> readBackupFile(String path) async {
  throw UnsupportedError('Not available on web');
}

Future<void> exportBackupWeb(BuildContext context, String json) async {
  await showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Backup JSON'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(child: SelectableText(json)),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close')),
      ],
    ),
  );
}
