library;

import 'src/init_stub.dart' if (dart.library.io) 'src/init_io.dart' as impl;

void initDatabaseFactory() => impl.initDatabaseFactory();
