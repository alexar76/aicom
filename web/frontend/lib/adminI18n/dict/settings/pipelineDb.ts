import type { I18nDict } from '../../types';

export const PIPELINE_DB_SETTINGS_DICT: I18nDict = {
  'settings.pipelineDb.title': {
    en: 'Pipeline database',
    ru: 'База данных пайплайна',
    es: 'Base de datos del pipeline',
  },
  'settings.pipelineDb.intro': {
    en: 'Default is SQLite on the data volume. Optionally migrate to PostgreSQL for external hosting or backups. After changing backend or URL, save settings and restart the app container.',
    ru: 'По умолчанию SQLite на томе данных. Можно мигрировать в PostgreSQL для внешнего хостинга или бэкапов. После смены backend или URL сохраните настройки и перезапустите контейнер app.',
    es: 'Por defecto SQLite en el volumen de datos. Opcionalmente migra a PostgreSQL para hosting externo o backups. Tras cambiar backend o URL, guarda ajustes y reinicia el contenedor app.',
  },
  'settings.pipelineDb.backend': { en: 'Backend', ru: 'Backend', es: 'Backend' },
  'settings.pipelineDb.sqlite': { en: 'SQLite (default)', ru: 'SQLite (по умолчанию)', es: 'SQLite (predeterminado)' },
  'settings.pipelineDb.postgres': { en: 'PostgreSQL', ru: 'PostgreSQL', es: 'PostgreSQL' },
  'settings.pipelineDb.jsonLegacy': {
    en: 'JSON file only (legacy)',
    ru: 'Только JSON-файл (legacy)',
    es: 'Solo archivo JSON (legacy)',
  },
  'settings.pipelineDb.pgUrl': {
    en: 'PostgreSQL connection URL',
    ru: 'URL подключения PostgreSQL',
    es: 'URL de conexión PostgreSQL',
  },
  'settings.pipelineDb.saved': { en: 'Saved:', ru: 'Сохранено:', es: 'Guardado:' },
  'settings.pipelineDb.effective': { en: 'Effective:', ru: 'Фактически:', es: 'Efectivo:' },
  'settings.pipelineDb.configured': {
    en: '(configured: {backend})',
    ru: '(в конфиге: {backend})',
    es: '(configurado: {backend})',
  },
  'settings.pipelineDb.sqliteStats': {
    en: 'SQLite: {products} products, {tasks} tasks',
    ru: 'SQLite: {products} продуктов, {tasks} задач',
    es: 'SQLite: {products} productos, {tasks} tareas',
  },
  'settings.pipelineDb.pgStats': {
    en: 'PostgreSQL: {products} products, {tasks} tasks',
    ru: 'PostgreSQL: {products} продуктов, {tasks} задач',
    es: 'PostgreSQL: {products} productos, {tasks} tareas',
  },
  'settings.pipelineDb.postgresError': {
    en: 'Postgres: {error}',
    ru: 'Postgres: {error}',
    es: 'Postgres: {error}',
  },
  'settings.pipelineDb.test': { en: 'Test connection', ru: 'Проверить подключение', es: 'Probar conexión' },
  'settings.pipelineDb.testing': { en: 'Testing…', ru: 'Проверка…', es: 'Probando…' },
  'settings.pipelineDb.migrate': {
    en: 'Migrate SQLite → Postgres',
    ru: 'Миграция SQLite → Postgres',
    es: 'Migrar SQLite → Postgres',
  },
  'settings.pipelineDb.migrating': { en: 'Migrating…', ru: 'Миграция…', es: 'Migrando…' },
  'settings.pipelineDb.migrateConfirm': {
    en: 'Copy all products and tasks from SQLite into PostgreSQL? Existing Postgres rows with the same IDs will be updated.',
    ru: 'Скопировать все продукты и задачи из SQLite в PostgreSQL? Существующие строки Postgres с теми же ID будут обновлены.',
    es: '¿Copiar todos los productos y tareas de SQLite a PostgreSQL? Las filas Postgres con los mismos ID se actualizarán.',
  },
  'settings.pipelineDb.migrateOk': {
    en: '✅ Migrated {products} products, {tasks} tasks → {dest}',
    ru: '✅ Мигрировано {products} продуктов, {tasks} задач → {dest}',
    es: '✅ Migrados {products} productos, {tasks} tareas → {dest}',
  },
  'settings.pipelineDb.testFailed': {
    en: 'Connection test failed',
    ru: 'Проверка подключения не удалась',
    es: 'Falló la prueba de conexión',
  },
  'settings.pipelineDb.migrateFailed': {
    en: 'Migration failed',
    ru: 'Миграция не удалась',
    es: 'Falló la migración',
  },
  'settings.pipelineDb.workflow': {
    en: 'Workflow: (1) enter URL and test connection, (2) migrate data, (3) set backend to PostgreSQL and save, (4) docker compose up --build -d app. You can also set PIPELINE_DATABASE_URL in .env.',
    ru: 'Порядок: (1) URL и тест, (2) миграция, (3) backend PostgreSQL и сохранение, (4) docker compose up --build -d app. Также можно задать PIPELINE_DATABASE_URL в .env.',
    es: 'Flujo: (1) URL y prueba, (2) migrar, (3) backend PostgreSQL y guardar, (4) docker compose up --build -d app. También PIPELINE_DATABASE_URL en .env.',
  },
};
