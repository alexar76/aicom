import type { I18nDict } from '../../types';

export const TELEGRAM_SETTINGS_DICT: I18nDict = {
  'settings.section.telegram': {
    en: 'Telegram alerts',
    ru: 'Оповещения Telegram',
    es: 'Alertas de Telegram',
  },
  'settings.telegram.intro': {
    en: 'Optional notifications when products are created and when each pipeline stage completes (same events as Corporate Chat). Create a bot with BotFather, copy the API token, then send any message to your bot and resolve chat id via https://api.telegram.org/bot<TOKEN>/getUpdates (look for chat.id).',
    ru: 'Необязательные уведомления при создании продуктов и на каждом этапе пайплайна (те же события, что в Corporate Chat). Создайте бота в BotFather, скопируйте токен API, затем отправьте любое сообщение боту и получите chat id через https://api.telegram.org/bot<TOKEN>/getUpdates (ищите chat.id).',
    es: 'Notificaciones opcionales al crear productos y al completar cada etapa del pipeline (mismos eventos que Corporate Chat). Crea un bot con BotFather, copia el token API, envía un mensaje al bot y resuelve el chat id con https://api.telegram.org/bot<TOKEN>/getUpdates (busca chat.id).',
  },
  'settings.telegram.botFather': {
    en: 'BotFather',
    ru: 'BotFather',
    es: 'BotFather',
  },
  'settings.telegram.sendMessageBold': {
    en: 'send any message to your bot',
    ru: 'отправьте любое сообщение боту',
    es: 'envía cualquier mensaje a tu bot',
  },
  'settings.telegram.chatIdBold': {
    en: 'chat id',
    ru: 'chat id',
    es: 'chat id',
  },
  'settings.telegram.enable': {
    en: 'Enable Telegram alerts',
    ru: 'Включить оповещения Telegram',
    es: 'Activar alertas de Telegram',
  },
  'settings.telegram.enableHelp': {
    en: 'Master switch — requires bot token and chat id.',
    ru: 'Главный переключатель — нужны токен бота и chat id.',
    es: 'Interruptor maestro — requiere token del bot y chat id.',
  },
  'settings.telegram.notifyStages': {
    en: 'Notify pipeline stages',
    ru: 'Уведомлять об этапах пайплайна',
    es: 'Notificar etapas del pipeline',
  },
  'settings.telegram.notifyProducts': {
    en: 'Notify new products',
    ru: 'Уведомлять о новых продуктах',
    es: 'Notificar productos nuevos',
  },
  'settings.telegram.chatId': {
    en: 'Telegram chat ID',
    ru: 'ID чата Telegram',
    es: 'ID de chat de Telegram',
  },
  'settings.telegram.chatIdPlaceholder': {
    en: 'e.g. "123456789" or "-1001234567890" for groups',
    ru: 'напр. «123456789» или «-1001234567890» для групп',
    es: 'p. ej. "123456789" o "-1001234567890" en grupos',
  },
  'settings.telegram.botTokenLabel': {
    en: 'Bot API token',
    ru: 'Токен API бота',
    es: 'Token API del bot',
  },
  'settings.telegram.botTokenPlaceholderKeep': {
    en: 'Leave blank to keep current token — enter only when rotating',
    ru: 'Оставьте пустым, чтобы сохранить текущий токен — вводите только при смене',
    es: 'Déjalo en blanco para conservar el token — escribe solo al rotar',
  },
  'settings.telegram.botTokenPlaceholderNew': {
    en: 'Paste token from BotFather',
    ru: 'Вставьте токен из BotFather',
    es: 'Pega el token de BotFather',
  },
  'settings.telegram.tokenHint': {
    en: 'Saved in config.yaml on the server (like other Settings secrets). Bot token is sent only when it looks complete (≥35 chars), then saves automatically after you stop typing.',
    ru: 'Сохраняется в config.yaml на сервере (как другие секреты в Настройках). Токен бота отправляется только если выглядит полным (≥35 символов), затем сохраняется автоматически после паузы в вводе.',
    es: 'Se guarda en config.yaml en el servidor (como otros secretos). El token solo se envía si parece completo (≥35 caracteres) y luego se guarda al dejar de escribir.',
  },
  'settings.telegram.tokenStored': {
    en: 'Token stored.',
    ru: 'Токен сохранён.',
    es: 'Token guardado.',
  },
  'settings.telegram.notConfigured': {
    en: 'Not configured.',
    ru: 'Не настроено.',
    es: 'No configurado.',
  },
  'settings.telegram.sendTest': {
    en: 'Send test message',
    ru: 'Отправить тестовое сообщение',
    es: 'Enviar mensaje de prueba',
  },
  'settings.telegram.sending': {
    en: 'Sending…',
    ru: 'Отправка…',
    es: 'Enviando…',
  },
  'settings.telegram.removeToken': {
    en: 'Remove bot token',
    ru: 'Удалить токен бота',
    es: 'Eliminar token del bot',
  },
  'settings.loading.telegram': {
    en: 'Loading…',
    ru: 'Загрузка…',
    es: 'Cargando…',
  },
  'settings.confirm.revokeTelegram': {
    en: 'Remove the stored Telegram bot token? Alerts will stop until you save a new token.',
    ru: 'Удалить сохранённый токен бота Telegram? Оповещения отключатся, пока не сохраните новый токен.',
    es: '¿Eliminar el token del bot guardado? Las alertas cesan hasta que guardes un token nuevo.',
  },
  'settings.toast.telegramTokenRemoved': {
    en: 'Telegram bot token removed',
    ru: 'Токен бота Telegram удалён',
    es: 'Token del bot de Telegram eliminado',
  },
  'settings.toast.telegramRevokeFailed': {
    en: 'Failed to revoke token',
    ru: 'Не удалось отозвать токен',
    es: 'Error al revocar el token',
  },
  'settings.toast.telegramTestSent': {
    en: 'Test message sent — check your Telegram chat',
    ru: 'Тестовое сообщение отправлено — проверьте чат в Telegram',
    es: 'Mensaje de prueba enviado — revisa tu chat de Telegram',
  },
  'settings.toast.telegramTestFailed': {
    en: 'Telegram test failed',
    ru: 'Тест Telegram не удался',
    es: 'Falló la prueba de Telegram',
  },
  'settings.toast.saveSettingsFailed': {
    en: 'Failed to save settings',
    ru: 'Не удалось сохранить настройки',
    es: 'Error al guardar los ajustes',
  },
  'settings.error.saveWithMessage': {
    en: '❌ Failed to save: {message}',
    ru: '❌ Не удалось сохранить: {message}',
    es: '❌ Error al guardar: {message}',
  },
  'settings.error.standupWithMessage': {
    en: '❌ Failed to save standup: {message}',
    ru: '❌ Не удалось сохранить стендап: {message}',
    es: '❌ Error al guardar standup: {message}',
  },
  'settings.error.triggerDirector': {
    en: '❌ Failed to trigger: {message}',
    ru: '❌ Не удалось запустить: {message}',
    es: '❌ Error al ejecutar: {message}',
  },
};
