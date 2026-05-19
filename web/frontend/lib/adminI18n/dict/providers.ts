import type { I18nDict } from '../types';

export const PROVIDERS_DICT: I18nDict = {
  'providers.title': {
    en: 'LLM Providers',
    ru: 'Провайдеры LLM',
    es: 'Proveedores LLM',
  },
  'providers.routingRules': { en: 'Routing Rules', ru: 'Правила маршрутизации', es: 'Reglas de enrutado' },
  'providers.addProvider': { en: 'Add Provider', ru: 'Добавить провайдера', es: 'Añadir proveedor' },
  'providers.defaultBadge': { en: 'Default', ru: 'По умолчанию', es: 'Predeterminado' },
  'providers.keyConfigured': { en: 'Key saved', ru: 'Ключ сохранён', es: 'Clave guardada' },
  'providers.keyMissing': { en: 'No API key', ru: 'Нет API-ключа', es: 'Sin clave API' },
  'providers.apiKeyStoredHint': {
    en: 'Key is stored on the server. Leave blank to keep the current key.',
    ru: 'Ключ сохранён на сервере. Оставьте поле пустым, чтобы не менять его.',
    es: 'La clave está guardada en el servidor. Deje vacío para conservarla.',
  },
  'providers.btn.refresh': { en: 'Refresh', ru: 'Обновить', es: 'Actualizar' },
  'providers.tooltip.testHeavy': {
    en: 'Test heavy model',
    ru: 'Проверить тяжёлую модель',
    es: 'Probar modelo pesado',
  },
  'providers.tooltip.editProvider': {
    en: 'Edit provider',
    ru: 'Редактировать провайдера',
    es: 'Editar proveedor',
  },
  'providers.btn.cancel': { en: 'Cancel', ru: 'Отмена', es: 'Cancelar' },
  'providers.btn.save': { en: 'Save', ru: 'Сохранить', es: 'Guardar' },
  'providers.btn.delete': { en: 'Delete', ru: 'Удалить', es: 'Eliminar' },
  'providers.circuit.title': {
    en: 'Circuit breaker — self-healing',
    ru: 'Circuit breaker — самовосстановление',
    es: 'Circuit breaker — autorrecuperación',
  },
  'providers.circuit.subtitle': {
    en: 'Per-provider resilience: CLOSED → OPEN after repeated failures → HALF_OPEN probe → CLOSED on success. Live via WebSocket.',
    ru: 'Устойчивость по провайдерам: CLOSED → OPEN при сбоях → HALF_OPEN проба → CLOSED при успехе. Live через WebSocket.',
    es: 'Resiliencia por proveedor: CLOSED → OPEN tras fallos → HALF_OPEN prueba → CLOSED al éxito. En vivo por WebSocket.',
  },
  'providers.circuit.policy': {
    en: '{threshold} failures / {window}s → OPEN · probe after {cooldown}s',
    ru: '{threshold} сбоев / {window}с → OPEN · проба через {cooldown}с',
    es: '{threshold} fallos / {window}s → OPEN · prueba tras {cooldown}s',
  },
  'providers.circuit.stateClosed': { en: 'CLOSED', ru: 'CLOSED', es: 'CLOSED' },
  'providers.circuit.stateOpen': { en: 'OPEN', ru: 'OPEN', es: 'OPEN' },
  'providers.circuit.stateHalfOpen': { en: 'HALF_OPEN', ru: 'HALF_OPEN', es: 'HALF_OPEN' },
  'providers.circuit.liveOn': { en: 'Live', ru: 'Live', es: 'En vivo' },
  'providers.circuit.liveOff': { en: 'Paused', ru: 'Пауза', es: 'Pausado' },
  'providers.circuit.loading': { en: 'Loading circuit state…', ru: 'Загрузка circuit…', es: 'Cargando circuit…' },
  'providers.circuit.empty': {
    en: 'No circuit data yet — run an LLM request or add a provider.',
    ru: 'Нет данных circuit — выполните LLM-запрос или добавьте провайдера.',
    es: 'Sin datos de circuit — ejecute una petición LLM o añada un proveedor.',
  },
  'providers.circuit.failuresWindow': {
    en: 'Failures (window)',
    ru: 'Сбои (окно)',
    es: 'Fallos (ventana)',
  },
  'providers.circuit.recovery': { en: 'Last recovery', ru: 'Посл. восстановление', es: 'Última recuperación' },
  'providers.circuit.untilHalfOpen': {
    en: 'Until HALF_OPEN',
    ru: 'До HALF_OPEN',
    es: 'Hasta HALF_OPEN',
  },
  'providers.circuit.lastError': { en: 'Last error', ru: 'Последняя ошибка', es: 'Último error' },
  'providers.circuit.forceOpen': { en: 'Force OPEN', ru: 'Принудительно OPEN', es: 'Forzar OPEN' },
  'providers.circuit.forceClose': { en: 'Force CLOSED', ru: 'Принудительно CLOSED', es: 'Forzar CLOSED' },
  'providers.circuit.reset': { en: 'Reset breaker', ru: 'Сбросить breaker', es: 'Reiniciar breaker' },
  'providers.circuit.actionDone': {
    en: 'Circuit {action} applied to {provider}',
    ru: 'Circuit {action} для {provider}',
    es: 'Circuit {action} en {provider}',
  },
};
