"""Shared SQLite FFI init for desktop Flutter apps (skipped on web)."""

import 'package:sqflite_common_ffi/sqflite_ffi.dart';

void initDatabaseFactory() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
}
