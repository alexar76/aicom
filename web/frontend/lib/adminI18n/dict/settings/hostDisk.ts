import type { I18nDict } from '../../types';

export const HOST_DISK_SETTINGS_DICT: I18nDict = {
  'settings.section.hostDisk': {
    en: 'Host disk alerts',
    ru: 'Алерты диска хоста',
    es: 'Alertas de disco del host',
  },
  'settings.hostDisk.intro': {
    en: 'Telegram warnings when data volume or root filesystem is low on space. Env vars (AIFACTORY_DISK_*) override these values on the running process until restart.',
    ru: 'Уведомления в Telegram при нехватке места на томе data или корневом разделе. Переменные окружения AIFACTORY_DISK_* переопределяют значения до перезапуска процесса.',
    es: 'Avisos por Telegram cuando el volumen data o el sistema de archivos raíz se quedan sin espacio. Las variables AIFACTORY_DISK_* anulan estos valores hasta reiniciar el proceso.',
  },
  'settings.hostDisk.telegramToggle': {
    en: 'Telegram alerts for disk space',
    ru: 'Telegram-алерты о диске',
    es: 'Alertas Telegram por espacio en disco',
  },
  'settings.hostDisk.telegramHelp': {
    en: 'Requires Telegram bot token + chat ID above. Same-level alert repeats at most once per cooldown.',
    ru: 'Нужны токен бота и chat ID в блоке Telegram выше. Повтор того же уровня — не чаще интервала ниже.',
    es: 'Requiere token del bot y chat ID en Telegram arriba. El mismo nivel se repite como máximo una vez por cooldown.',
  },
  'settings.hostDisk.warnUsedPct': {
    en: 'Warning — used %',
    ru: 'Предупреждение — занято %',
    es: 'Aviso — % usado',
  },
  'settings.hostDisk.critUsedPct': {
    en: 'Critical — used %',
    ru: 'Критично — занято %',
    es: 'Crítico — % usado',
  },
  'settings.hostDisk.warnFreeGb': {
    en: 'Warning — free below (GB)',
    ru: 'Предупреждение — свободно меньше (ГБ)',
    es: 'Aviso — libre por debajo de (GB)',
  },
  'settings.hostDisk.critFreeGb': {
    en: 'Critical — free below (GB)',
    ru: 'Критично — свободно меньше (ГБ)',
    es: 'Crítico — libre por debajo de (GB)',
  },
  'settings.hostDisk.cooldownHours': {
    en: 'Repeat same level (hours)',
    ru: 'Повтор того же уровня (часы)',
    es: 'Repetir mismo nivel (horas)',
  },
  'settings.hostDisk.intervalMinutes': {
    en: 'Check interval (minutes)',
    ru: 'Интервал проверки (минуты)',
    es: 'Intervalo de comprobación (minutos)',
  },
  'settings.hostDisk.liveTitle': {
    en: 'Current host status',
    ru: 'Текущее состояние хоста',
    es: 'Estado actual del host',
  },
  'settings.hostDisk.liveOk': {
    en: 'OK',
    ru: 'Норма',
    es: 'OK',
  },
  'settings.hostDisk.liveWarning': {
    en: 'Warning',
    ru: 'Предупреждение',
    es: 'Aviso',
  },
  'settings.hostDisk.liveCritical': {
    en: 'Critical',
    ru: 'Критично',
    es: 'Crítico',
  },
  'settings.hostDisk.pathLine': {
    en: '{path}: {used}% used, {free} GB free',
    ru: '{path}: занято {used}%, свободно {free} ГБ',
    es: '{path}: {used}% usado, {free} GB libres',
  },
  'settings.hostDisk.envOverride': {
    en: 'Effective thresholds may differ if AIFACTORY_DISK_* env vars are set on this host.',
    ru: 'Фактические пороги могут отличаться, если на хосте заданы AIFACTORY_DISK_* в окружении.',
    es: 'Los umbrales efectivos pueden diferir si hay variables AIFACTORY_DISK_* en el host.',
  },
};
