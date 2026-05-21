import type { I18nDict } from '../../types';

export const FACTORY_BACKUP_SETTINGS_DICT: I18nDict = {
  'settings.factoryBackup.title': {
    en: 'Factory backup & restore',
    ru: 'Бэкап и восстановление фабрики',
    es: 'Copia y restauración de la fábrica',
  },
  'settings.factoryBackup.body': {
    en: 'Full snapshot of the data volume (not a merge). Backup downloads a ZIP; restore replaces all live data after confirmations. A pre-restore ZIP is saved under data/backups/ automatically.',
    ru: 'Полный слепок тома data (не слияние). Бэкап — ZIP; восстановление заменяет все данные после подтверждений. Перед restore автоматически сохраняется ZIP в data/backups/.',
    es: 'Instantánea completa del volumen data (no es fusión). La copia descarga un ZIP; restaurar reemplaza todos los datos tras confirmaciones. Se guarda un ZIP previo en data/backups/.',
  },
  'settings.factoryBackup.download': {
    en: 'Download full factory ZIP',
    ru: 'Скачать полный ZIP фабрики',
    es: 'Descargar ZIP completo de la fábrica',
  },
  'settings.factoryBackup.includeSandboxes': {
    en: 'Include sandboxes (large)',
    ru: 'Включить sandboxes (тяжёлые)',
    es: 'Incluir sandboxes (grandes)',
  },
  'settings.factoryBackup.roleHint': {
    en: 'Admin or super_admin only. Contains secrets — store offline securely.',
    ru: 'Только admin / super_admin. Содержит секреты — храните офлайн.',
    es: 'Solo admin / super_admin. Incluye secretos — guárdelo offline.',
  },
  'settings.factoryBackup.productZipHint': {
    en: 'Per-product export: Admin → Files → Download product ZIP.',
    ru: 'Экспорт одного продукта: Admin → Files → Download product ZIP.',
    es: 'Exportar un producto: Admin → Files → Download product ZIP.',
  },
  'settings.factoryBackup.failed': {
    en: 'Factory backup download failed',
    ru: 'Не удалось скачать бэкап фабрики',
    es: 'Error al descargar la copia de la fábrica',
  },
  'settings.factoryBackup.demoBlocked': {
    en: 'Public demo: backup and restore are disabled so shared products and the demo admin password stay intact. Self-host for full owner controls.',
    ru: 'Публичное демо: бэкап и восстановление отключены, чтобы не ломать общие продукты и пароль admin. Для полного контроля — свой инстанс.',
    es: 'Demo público: copia y restauración desactivadas para proteger productos compartidos y la contraseña demo. Autoaloje su instancia.',
  },
  'settings.factoryBackup.restoreTitle': {
    en: 'Restore from backup (full replace)',
    ru: 'Восстановление из бэкапа (полная замена)',
    es: 'Restaurar desde copia (reemplazo total)',
  },
  'settings.factoryBackup.restoreHint': {
    en: 'Upload a factory backup ZIP created on this or another instance. Preview shows warnings; restore replaces pipeline, settings, secrets, and all product folders.',
    ru: 'Загрузите ZIP бэкапа с этого или другого инстанса. Превью покажет предупреждения; restore заменит pipeline, настройки, секреты и все папки продуктов.',
    es: 'Suba un ZIP de copia de esta u otra instancia. La vista previa muestra avisos; restaurar reemplaza pipeline, ajustes, secretos y carpetas de productos.',
  },
  'settings.factoryBackup.chooseZip': {
    en: 'Choose backup .zip',
    ru: 'Выбрать backup .zip',
    es: 'Elegir backup .zip',
  },
  'settings.factoryBackup.preview': {
    en: 'Preview restore',
    ru: 'Превью восстановления',
    es: 'Vista previa',
  },
  'settings.factoryBackup.previewFailed': {
    en: 'Restore preview failed',
    ru: 'Не удалось сделать превью',
    es: 'Error en vista previa',
  },
  'settings.factoryBackup.currentProducts': {
    en: 'Current products in pipeline',
    ru: 'Продуктов в pipeline сейчас',
    es: 'Productos actuales en pipeline',
  },
  'settings.factoryBackup.backupFrom': {
    en: 'Backup created',
    ru: 'Бэкап создан',
    es: 'Copia creada',
  },
  'settings.factoryBackup.warnings': {
    en: 'Warnings',
    ru: 'Предупреждения',
    es: 'Advertencias',
  },
  'settings.factoryBackup.confirmReplace': {
    en: 'I understand this will REPLACE all factory data (full snapshot, not merge)',
    ru: 'Понимаю: все данные фабрики будут ЗАМЕНЕНЫ (полный слепок, не слияние)',
    es: 'Entiendo que esto REEMPLAZARÁ todos los datos (instantánea completa, no fusión)',
  },
  'settings.factoryBackup.confirmTrusted': {
    en: 'This backup ZIP is from a trusted source',
    ru: 'ZIP бэкапа из доверенного источника',
    es: 'Este ZIP proviene de una fuente confiable',
  },
  'settings.factoryBackup.confirmSaved': {
    en: 'I downloaded a fresh backup of the current state (or accept auto pre-restore ZIP in data/backups/)',
    ru: 'Скачал свежий бэкап текущего состояния (или принимаю авто-ZIP в data/backups/ перед restore)',
    es: 'Descargué una copia del estado actual (o acepto el ZIP automático en data/backups/)',
  },
  'settings.factoryBackup.runRestore': {
    en: 'Restore factory now',
    ru: 'Восстановить фабрику',
    es: 'Restaurar ahora',
  },
  'settings.factoryBackup.restoreDone': {
    en: 'Restore completed — restart the app container',
    ru: 'Восстановление завершено — перезапустите контейнер app',
    es: 'Restauración completada — reinicie el contenedor app',
  },
  'settings.factoryBackup.restoreFailed': {
    en: 'Factory restore failed',
    ru: 'Восстановление не удалось',
    es: 'Error al restaurar',
  },
};
