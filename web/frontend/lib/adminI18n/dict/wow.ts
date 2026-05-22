import type { I18nDict } from '../types';

export const WOW_DICT: I18nDict = {
  'wow.factoryFloorIntro': {
    en: 'Real-time agent graph — latency, cost, circuit breakers. Powered by /api/admin/ws/metrics.',
    ru: 'Граф агентов в реальном времени — latency, стоимость, circuit breaker. WebSocket метрик.',
    es: 'Grafo de agentes en tiempo real — latencia, coste, circuit breakers.',
  },
  'wow.factoryFloorLive': {
    en: 'live',
    ru: 'live',
    es: 'en vivo',
  },
  'wow.factoryFloorSyncing': {
    en: 'syncing…',
    ru: 'синхронизация…',
    es: 'sincronizando…',
  },
  'wow.factoryFloorStale': {
    en: 'cached (reconnecting)',
    ru: 'кэш (переподключение)',
    es: 'caché (reconectando)',
  },
  'wow.factoryFloorReconnecting': {
    en: 'reconnecting…',
    ru: 'переподключение…',
    es: 'reconectando…',
  },
  'wow.factoryFloorLoadFailed': {
    en: 'Could not load graph — retrying',
    ru: 'Не удалось загрузить граф — повтор',
    es: 'No se pudo cargar el grafo — reintentando',
  },
  'wow.factoryFloorCachedSync': {
    en: 'Showing cached graph — refreshing live metrics in the background.',
    ru: 'Показан кэш графа — актуальные метрики подгружаются в фоне.',
    es: 'Gráfico en caché — actualizando métricas en vivo en segundo plano.',
  },
  'wow.factoryFloorFirstLoad': {
    en: 'Loading live factory floor…',
    ru: 'Загрузка live Factory Floor…',
    es: 'Cargando Factory Floor en vivo…',
  },
  'wow.timeTravelIntro': {
    en: 'Scrub the pipeline timeline and fork an alternate branch from any frame.',
    ru: 'Прокрутка таймлайна пайплайна и форк альтернативной ветки с любого кадра.',
    es: 'Recorre la línea temporal del pipeline y bifurca desde cualquier frame.',
  },
  'wow.showcaseIntro': {
    en: 'Auto-captured Playwright clips for shipped products (docs/gallery).',
    ru: 'Авто-запись Playwright для готовых продуктов (docs/gallery).',
    es: 'Clips Playwright auto-capturados para productos publicados.',
  },
  'wow.showcaseProductId': {
    en: 'Product ID',
    ru: 'ID продукта',
    es: 'ID del producto',
  },
  'wow.showcaseRecord': {
    en: 'Record showcase',
    ru: 'Записать витрину',
    es: 'Grabar escaparate',
  },
  'wow.showcaseRecording': {
    en: 'Recording…',
    ru: 'Запись…',
    es: 'Grabando…',
  },
  'wow.showcaseQueued': {
    en: 'Showcase queued — Playwright is capturing the sandbox preview.',
    ru: 'Запись в очереди — Playwright снимает превью sandbox.',
    es: 'Grabación en cola — Playwright captura la vista previa del sandbox.',
  },
  'wow.showcaseAlreadyQueued': {
    en: 'Already recording this product — wait for the current job to finish.',
    ru: 'Этот продукт уже записывается — дождитесь завершения текущей задачи.',
    es: 'Este producto ya se está grabando — espere a que termine el trabajo actual.',
  },
  'wow.showcaseDone': {
    en: 'Showcase clip ready in the gallery.',
    ru: 'Клип витрины готов — смотрите в галерее ниже.',
    es: 'Clip del escaparate listo — véalo en la galería.',
  },
  'wow.showcaseFailed': {
    en: 'Showcase capture failed',
    ru: 'Не удалось записать витрину',
    es: 'Falló la grabación del escaparate',
  },
  'wow.showcaseOpenPreview': {
    en: 'Open preview',
    ru: 'Открыть превью',
    es: 'Abrir vista previa',
  },
  'wow.showcaseEmpty': {
    en: 'No showcase clips yet — enter a shipped product ID and press Record.',
    ru: 'Клипов пока нет — укажите ID доставленного продукта и нажмите «Записать витрину».',
    es: 'Aún no hay clips — indique el ID de un producto enviado y pulse Grabar.',
  },
  'wow.promptLoopIntro': {
    en: 'Meta-agent analyzes failed tasks and proposes prompt patches with A/B apply.',
    ru: 'Мета-агент анализирует провалы и предлагает патчи промптов с A/B.',
    es: 'Meta-agente analiza fallos y propone parches de prompts con A/B.',
  },
  'wow.costHeatmapTitle': {
    en: 'Cost per completed product',
    ru: 'Стоимость на завершённый продукт',
    es: 'Coste por producto completado',
  },
  'wow.costHeatmapIntro': {
    en: 'LLM spend for products in Completed or Deployed state — from llm_calls.jsonl, grouped by product and agent.',
    ru: 'Расход LLM по продуктам в статусе Completed/Deployed — из llm_calls.jsonl, по продукту и агенту.',
    es: 'Gasto LLM por productos Completed/Deployed — desde llm_calls.jsonl, por producto y agente.',
  },
  'wow.costHeatmapTotal': { en: 'Total LLM spend', ru: 'Всего LLM', es: 'Gasto LLM total' },
  'wow.costHeatmapProductCount': {
    en: '{count} completed product(s)',
    ru: '{count} заверш. продукт(ов)',
    es: '{count} producto(s) completado(s)',
  },
  'wow.costHeatmapNoCalls': {
    en: 'No LLM calls logged for this product',
    ru: 'Нет LLM-вызовов для этого продукта',
    es: 'Sin llamadas LLM para este producto',
  },
  'wow.costHeatmapCalls': {
    en: '{count} LLM call(s)',
    ru: '{count} LLM-вызов(ов)',
    es: '{count} llamada(s) LLM',
  },
  'wow.costHeatmapAllZero': {
    en: 'Products are completed but no LLM cost is attributed yet — calls may lack product_id in logs, or spend happened before logging was enabled.',
    ru: 'Продукты завершены, но LLM-расход не привязан — в логах может не быть product_id или учёт включили позже.',
    es: 'Productos completados sin coste LLM atribuido — puede faltar product_id en logs o el registro se activó después.',
  },
  'wow.costHeatmapStateCompleted': { en: 'Completed', ru: 'Completed', es: 'Completed' },
  'wow.costHeatmapStateDeployed': { en: 'Deployed', ru: 'Deployed', es: 'Deployed' },
  'wow.costHeatmapEmpty': {
    en: 'No LLM cost data for completed products yet.',
    ru: 'Пока нет данных LLM-стоимости по завершённым продуктам.',
    es: 'Aún no hay datos de coste LLM para productos completados.',
  },
  'wow.aimarketEmbed': {
    en: 'Embed: <script src="/aimarket.js" data-product="prod-…" data-price="9.99"></script>',
    ru: 'Встраивание: <script src="/aimarket.js" data-product="prod-…" data-price="9.99"></script>',
    es: 'Embed: <script src="/aimarket.js" data-product="prod-…" data-price="9.99"></script>',
  },
};
