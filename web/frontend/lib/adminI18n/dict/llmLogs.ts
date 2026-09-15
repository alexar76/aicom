import type { I18nDict } from '../types';

/** LLM call logs tab — header and common chrome. */
export const LLM_LOGS_DICT: I18nDict = {
  'llmLogs.title': {
    en: 'LLM Call Logs',
    ru: 'Журнал вызовов LLM',
    es: 'Registros de llamadas LLM',
    fr: 'Journaux des appels LLM',
    zh: 'LLM 调用日志',
  },
  'llmLogs.intro': {
    en:
      'Estimates use input/output rates when the API reports prompt and completion tokens; otherwise blended $/Mtok and heavy/light provider rates from routing (llm_pricing.example.yaml) — not a vendor invoice. The table loads rows at a time (newest first); use Load more for older pages. With a time range, totals and charts on the server cover every matching call, not only the loaded rows.',
    ru:
      'Оценки строятся по входным/выходным тарифам, если API отдаёт токены prompt и completion; иначе — смешанные $/Mtok и ставки heavy/light из маршрутизации (llm_pricing.example.yaml), это не счёт провайдера. Таблица подгружается порциями (сначала новые); для старых — «ещё». При диапазоне времени суммы и диаграммы на сервере покрывают все совпадающие вызовы, не только загруженные строки.',
    es:
      'Las estimaciones usan tarifas entrada/salida cuando la API informa tokens; si no, $/Mtok mezclado y tasas heavy/light del enrutamiento (llm_pricing.example.yaml) — no es factura del proveedor. La tabla carga filas por lotes (más nuevas primero); usa cargar más para páginas antiguas. Con rango temporal, los totales y gráficos del servidor cubren todas las llamadas coincidentes, no solo las filas cargadas.',
    fr:
      'Les estimations utilisent les tarifs entrée/sortie lorsque l\'API renvoie les jetons prompt et completion ; sinon, $/Mtok mixte et tarifs de fournisseur heavy/light issus du routage (llm_pricing.example.yaml) — ce n\'est pas une facture du fournisseur. Le tableau charge les lignes par lots (les plus récentes d\'abord) ; utilisez Charger plus pour les pages plus anciennes. Avec une plage de temps, les totaux et graphiques côté serveur couvrent tous les appels correspondants, pas seulement les lignes chargées.',
    zh:
      '当 API 报告 prompt 和 completion 令牌时，估算使用输入/输出费率；否则使用来自路由 (llm_pricing.example.yaml) 的混合 $/Mtok 及 heavy/light 提供方费率 — 这并非供应商账单。表格按批加载行（最新的在前）；使用"加载更多"查看较早的页面。设置时间范围时，服务器上的合计和图表涵盖所有匹配的调用，而不仅是已加载的行。',
  },
  'llmLogs.btn.refresh': { en: 'Refresh', ru: 'Обновить', es: 'Actualizar', fr: 'Actualiser', zh: '刷新' },
  'llmLogs.loading.logs': { en: 'Loading logs…', ru: 'Загрузка логов…', es: 'Cargando registros…', fr: 'Chargement des journaux…', zh: '正在加载日志…' },
  'llmLogs.loading.short': {
    en: 'Loading…',
    ru: 'Загрузка…',
    es: 'Cargando…',
    fr: 'Chargement…',
    zh: '加载中…',
  },
  'llmLogs.btn.loadMore': { en: 'Load more', ru: 'Загрузить ещё', es: 'Cargar más', fr: 'Charger plus', zh: '加载更多' },
  'llmLogs.empty.server': {
    en: 'No LLM calls in the current server filter.',
    ru: 'Нет вызовов LLM по текущему фильтру на сервере.',
    es: 'No hay llamadas LLM con el filtro actual del servidor.',
    fr: 'Aucun appel LLM dans le filtre serveur actuel.',
    zh: '当前服务器筛选条件下没有 LLM 调用。',
  },
  'llmLogs.empty.hint': {
    en: 'Try another provider or time range, or refresh after new traffic.',
    ru: 'Смените провайдера или диапазон дат, либо обновите после новых запросов.',
    es: 'Pruebe otro proveedor o rango de fechas, o actualice tras nuevo tráfico.',
    fr: 'Essayez un autre fournisseur ou une autre plage de temps, ou actualisez après un nouveau trafic.',
    zh: '尝试其他提供方或时间范围，或在有新流量后刷新。',
  },
  'llmLogs.error.load': {
    en: 'Could not load LLM logs',
    ru: 'Не удалось загрузить LLM-логи',
    es: 'No se pudieron cargar los registros LLM',
    fr: 'Impossible de charger les journaux LLM',
    zh: '无法加载 LLM 日志',
  },
  'llmLogs.error.auth': {
    en: 'Sign in again at /admin/login (admin session expired or missing).',
    ru: 'Войдите снова на /admin/login (сессия админа истекла или отсутствует).',
    es: 'Inicie sesión de nuevo en /admin/login (sesión admin caducada o ausente).',
    fr: 'Reconnectez-vous sur /admin/login (session admin expirée ou absente).',
    zh: '请在 /admin/login 重新登录（管理员会话已过期或缺失）。',
  },
};
