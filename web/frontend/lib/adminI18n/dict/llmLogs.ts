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
};
