import type { I18nDict } from '../types';

/** LLM call logs tab — header and common chrome. */
export const LLM_LOGS_DICT: I18nDict = {
  'llmLogs.title': {
    en: 'LLM Call Logs',
    ru: 'Журнал вызовов LLM',
    es: 'Registros de llamadas LLM',
  },
  'llmLogs.intro': {
    en:
      'Estimates use input/output rates when the API reports prompt and completion tokens; otherwise blended $/Mtok and heavy/light provider rates from routing (llm_pricing.example.yaml) — not a vendor invoice. The table loads rows at a time (newest first); use Load more for older pages. With a time range, totals and charts on the server cover every matching call, not only the loaded rows.',
    ru:
      'Оценки строятся по входным/выходным тарифам, если API отдаёт токены prompt и completion; иначе — смешанные $/Mtok и ставки heavy/light из маршрутизации (llm_pricing.example.yaml), это не счёт провайдера. Таблица подгружается порциями (сначала новые); для старых — «ещё». При диапазоне времени суммы и диаграммы на сервере покрывают все совпадающие вызовы, не только загруженные строки.',
    es:
      'Las estimaciones usan tarifas entrada/salida cuando la API informa tokens; si no, $/Mtok mezclado y tasas heavy/light del enrutamiento (llm_pricing.example.yaml) — no es factura del proveedor. La tabla carga filas por lotes (más nuevas primero); usa cargar más para páginas antiguas. Con rango temporal, los totales y gráficos del servidor cubren todas las llamadas coincidentes, no solo las filas cargadas.',
  },
  'llmLogs.btn.refresh': { en: 'Refresh', ru: 'Обновить', es: 'Actualizar' },
  'llmLogs.loading.logs': { en: 'Loading logs…', ru: 'Загрузка логов…', es: 'Cargando registros…' },
  'llmLogs.loading.short': {
    en: 'Loading…',
    ru: 'Загрузка…',
    es: 'Cargando…',
  },
  'llmLogs.btn.loadMore': { en: 'Load more', ru: 'Загрузить ещё', es: 'Cargar más' },
  'llmLogs.empty.server': {
    en: 'No LLM calls in the current server filter.',
    ru: 'Нет вызовов LLM по текущему фильтру на сервере.',
    es: 'No hay llamadas LLM con el filtro actual del servidor.',
  },
  'llmLogs.empty.hint': {
    en: 'Try another provider or time range, or refresh after new traffic.',
    ru: 'Смените провайдера или диапазон дат, либо обновите после новых запросов.',
    es: 'Pruebe otro proveedor o rango de fechas, o actualice tras nuevo tráfico.',
  },
  'llmLogs.error.load': {
    en: 'Could not load LLM logs',
    ru: 'Не удалось загрузить LLM-логи',
    es: 'No se pudieron cargar los registros LLM',
  },
  'llmLogs.error.auth': {
    en: 'Sign in again at /admin/login (admin session expired or missing).',
    ru: 'Войдите снова на /admin/login (сессия админа истекла или отсутствует).',
    es: 'Inicie sesión de nuevo en /admin/login (sesión admin caducada o ausente).',
  },
};
