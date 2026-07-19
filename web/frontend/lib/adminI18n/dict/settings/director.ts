import type { I18nDict } from '../../types';

export const DIRECTOR_SETTINGS_DICT: I18nDict = {
  'settings.pageTitle': {
    en: 'Settings',
    ru: 'Настройки',
    es: 'Ajustes',
  },
  'settings.section.directorPipeline': {
    en: 'AI Director & pipeline mode',
    ru: 'AI Director и режим пайплайна',
    es: 'AI Director y modo de pipeline',
  },
  'settings.director.intro': {
    en: 'The AI Director oversees products and analysis. Use autonomous development to create new products on a schedule, or turn it off and submit ideas manually (CLI / admin).',
    ru: 'AI Director курирует продукты и аналитику. Включите автономную разработку для периодического добавления продуктов или отключите и подавайте идеи вручную (CLI / админка).',
    es: 'El AI Director supervisa productos y análisis. Activa desarrollo autónomo para crear productos por calendario, o desactívalo y envía ideas manualmente (CLI / admin).',
  },
  'settings.loading.short': {
    en: 'Loading settings…',
    ru: 'Загрузка настроек…',
    es: 'Cargando ajustes…',
  },
  'settings.toggle.autonomousDev': {
    en: 'Autonomous development',
    ru: 'Автономная разработка',
    es: 'Desarrollo autónomo',
  },
  'settings.toggle.autonomousDev.help': {
    en: 'On: scheduled market research + idea generation enqueue products into the same pipeline. Off: new products only when you submit a brief (Admin / CLI).',
    ru: 'Вкл.: по расписанию исследование рынка + генерация идей ставит продукты в тот же пайплайн. Выкл.: новые продукты только при подаче брифа (админка / CLI).',
    es: 'Activado: investigación de mercado e ideas programadas encolan productos en el mismo pipeline. Desactivado: productos nuevos solo al enviar un brief (Admin / CLI).',
  },
  'settings.director.cadence': {
    en: 'Cadence: at most one auto-enqueued product per {minutes} minutes (Director checks every ~30s).',
    ru: 'Каденция: не более одного авто‑продукта за {minutes} мин. (Director проверяет раз в ~30 с).',
    es: 'Cadencia: como mucho un producto auto‑encolado cada {minutes} minutos (Director revisa cada ~30 s).',
  },
  'settings.director.minIntervalLabel': {
    en: 'Minimum interval between auto-generated products (minutes)',
    ru: 'Минимальный интервал между автогенерируемыми продуктами (минуты)',
    es: 'Intervalo mínimo entre productos autogenerados (minutos)',
  },
  'settings.director.intervalHint': {
    en: 'Range 15 minutes … 7 days (10080 min). Changes save automatically after a short pause.',
    ru: 'Диапазон 15 минут … 7 дней (10080 мин). Изменения сохраняются автоматически после паузы.',
    es: 'Rango 15 minutos … 7 días (10080 min). Los cambios se guardan solos tras una breve pausa.',
  },
  'settings.toggle.pipelineCostOptimized': {
    en: 'Optimized token spend (recommended)',
    ru: 'Оптимизированный расход токенов (рекомендуется)',
    es: 'Gasto de tokens optimizado (recomendado)',
  },
  'settings.toggle.pipelineCostOptimized.help': {
    en: 'Caps pre-ship QA repair ($5/product, 10 rounds, 8 for landings) and keeps post-ship analyst monitoring from auto-queueing full developer regens. Turn off for unlimited repair budget (legacy). Individual fields remain editable under Pipeline & product quality.',
    ru: 'Ограничивает pre-ship QA-repair ($5/продукт, 10 раундов, 8 для лендингов) и не даёт post-ship мониторингу автоматически ставить полный regen в developer. Выкл. — без лимитов (legacy). Поля можно менять в «Качество пайплайна».',
    es: 'Limita el repair pre-ship ($5/producto, 10 rondas, 8 en landings) y evita que el monitoreo post-ship encole regens completos del developer. Desactivar = presupuesto legacy sin tope. Los campos siguen editables en Calidad del pipeline.',
  },
  'settings.toggle.highThroughput': {
    en: 'Local high-throughput mode',
    ru: 'Локальный высокопроизводительный режим',
    es: 'Modo local de alto rendimiento',
  },
  'settings.toggle.highThroughput.help': {
    en: 'For a powerful local machine (many cores / RAM, local Ollama): raises how many pipeline tasks can run at once, batch intake per cycle, and parallel agent execution. Turn off on small VMs or shared cloud — you can overload GPUs or hit API rate limits. Non-empty AIFACTORY_* env vars still override each knob. Task limits pick up from saved config automatically; the LLM router reads its limits at worker start — restart the pipeline worker after toggling this if you rely on changed LLM parallelism.',
    ru: 'Для мощной локальной машины (много ядер / RAM, локальный Ollama): повышает число параллельных задач пайплайна, размер пакета за цикл и параллельность агентов. Отключайте на слабых VM или в shared cloud — можно перегрузить GPU или упереться в лимиты API. Непустые AIFACTORY_* в env переопределяют параметры. Лимиты задач подхватываются из сохранённой конфигурации; LLM‑роутер читает лимиты при старте воркера — перезапустите воркер пайплайна после переключения, если важна изменённая параллельность LLM.',
    es: 'Para un equipo local potente (muchos núcleos / RAM, Ollama local): sube cuántas tareas del pipeline pueden ejecutarse a la vez, el lote por ciclo y la ejecución paralela de agentes. Desactívalo en VMs pequeñas o nube compartida: puedes saturar GPUs o topar rate limits. Las variables AIFACTORY_* no vacías siguen anulando cada ajuste. Los límites de tareas salen de la config guardada; el router LLM lee sus límites al iniciar el worker — reinicia el worker si dependes del paralelismo LLM cambiado.',
  },
  'settings.throughput.title': {
    en: 'Effective throughput (this host)',
    ru: 'Эффективная пропускная способность (этот хост)',
    es: 'Rendimiento efectivo (este host)',
  },
  'settings.throughput.envHint': {
    en: 'Same rules as the pipeline worker: non-empty AIFACTORY_* env overrides each value. LLM router still uses its semaphore from worker start — this table shows what would apply to a new process now.',
    ru: 'Те же правила, что у воркера пайплайна: непустые AIFACTORY_* в env переопределяют значения. LLM‑роутер всё равно использует семафор со старта воркера — таблица показывает, что применилось бы к новому процессу сейчас.',
    es: 'Mismas reglas que el worker del pipeline: env AIFACTORY_* no vacío anula cada valor. El router LLM sigue usando su semáforo desde el inicio del worker — la tabla muestra qué aplicaría a un proceso nuevo ahora.',
  },
  'settings.throughput.turboPreset': {
    en: 'Turbo preset in config',
    ru: 'Turbo‑пресет в конфиге',
    es: 'Preset turbo en la config',
  },
  'settings.throughput.on': {
    en: 'on',
    ru: 'вкл.',
    es: 'sí',
  },
  'settings.throughput.off': {
    en: 'off',
    ru: 'выкл.',
    es: 'no',
  },
  'settings.throughput.maxRunningTasks': {
    en: 'Max running tasks',
    ru: 'Макс. запущенных задач',
    es: 'Tareas en ejecución máx.',
  },
  'settings.throughput.taskExecutorConcurrency': {
    en: 'Task executor concurrency',
    ru: 'Параллелизм исполнителя задач',
    es: 'Concurrencia del ejecutor de tareas',
  },
  'settings.throughput.batchStartsPerCycle': {
    en: 'Batch starts / cycle',
    ru: 'Стартов батча / цикл',
    es: 'Inicios por lote / ciclo',
  },
  'settings.throughput.batchActiveCeiling': {
    en: 'Batch active ceiling',
    ru: 'Потолок активных батча',
    es: 'Techo de lote activo',
  },
  'settings.throughput.llmMaxParallel': {
    en: 'LLM max parallel',
    ru: 'LLM макс. параллельно',
    es: 'LLM máx. en paralelo',
  },
  'settings.throughput.llmMinIntervalSec': {
    en: 'LLM min interval (sec)',
    ru: 'LLM мин. интервал (сек)',
    es: 'LLM intervalo mín. (s)',
  },
  'settings.throughput.llmMaxRpm': {
    en: 'LLM max RPM',
    ru: 'LLM макс. RPM',
    es: 'LLM máx. RPM',
  },
  'settings.throughput.llmDailyCapUsd': {
    en: 'LLM daily cap (USD)',
    ru: 'LLM дневной лимит (USD)',
    es: 'LLM tope diario (USD)',
  },
  'settings.throughput.llmMonthlyCapUsd': {
    en: 'LLM monthly cap (USD)',
    ru: 'LLM месячный лимит (USD)',
    es: 'LLM tope mensual (USD)',
  },
  'settings.throughput.snapshotUnavailable': {
    en: 'Snapshot not available.',
    ru: 'Снимок недоступен.',
    es: 'Instantánea no disponible.',
  },
  'settings.btn.refresh': {
    en: 'Refresh',
    ru: 'Обновить',
    es: 'Actualizar',
  },
  'settings.autogenModal.title': {
    en: 'How often should auto-generation run?',
    ru: 'Как часто запускать автогенерацию?',
    es: '¿Con qué frecuencia debe ejecutarse la autogeneración?',
  },
  'settings.autogenModal.body': {
    en: 'The autonomous pipeline enqueues at most one new product per interval. Director re-reads settings about every 30 seconds.',
    ru: 'Автономный пайплайн ставит в очередь не более одного нового продукта за интервал. Director перечитывает настройки примерно каждые 30 секунд.',
    es: 'El pipeline autónomo encola como mucho un producto nuevo por intervalo. Director vuelve a leer la configuración cada ~30 segundos.',
  },
  'settings.autogenModal.preset15m': { en: '15 min', ru: '15 мин', es: '15 min' },
  'settings.autogenModal.preset30m': { en: '30 min', ru: '30 мин', es: '30 min' },
  'settings.autogenModal.preset1h': { en: '1 h', ru: '1 ч', es: '1 h' },
  'settings.autogenModal.preset6h': { en: '6 h', ru: '6 ч', es: '6 h' },
  'settings.autogenModal.preset12h': { en: '12 h', ru: '12 ч', es: '12 h' },
  'settings.autogenModal.preset24h': { en: '24 h', ru: '24 ч', es: '24 h' },
  'settings.label.customIntervalMinutes': {
    en: 'Custom interval (minutes)',
    ru: 'Свой интервал (минуты)',
    es: 'Intervalo personalizado (minutos)',
  },
  'settings.modal.cancel': {
    en: 'Cancel',
    ru: 'Отмена',
    es: 'Cancelar',
  },
  'settings.modal.enable': {
    en: 'Enable',
    ru: 'Включить',
    es: 'Activar',
  },
  'settings.modal.saving': {
    en: 'Saving…',
    ru: 'Сохранение…',
    es: 'Guardando…',
  },
  'settings.directorManualHint': {
    en: 'Manually trigger Director AI to run an analysis cycle and generate a report now.',
    ru: 'Вручную запустите цикл анализа Director и сгенерируйте отчёт сейчас.',
    es: 'Dispara manualmente un ciclo de análisis del Director y genera un informe ya.',
  },
  'settings.btn.triggerDirector': {
    en: 'Trigger Director Analysis Now',
    ru: 'Запустить анализ Director сейчас',
    es: 'Ejecutar análisis del Director ya',
  },
  'settings.director.triggering': {
    en: 'Triggering…',
    ru: 'Запуск…',
    es: 'Ejecutando…',
  },
  'settings.toast.autoGenOff': {
    en: 'Auto-generation turned off',
    ru: 'Автогенерация выключена',
    es: 'Autogeneración desactivada',
  },
  'settings.toast.saveFailed': {
    en: 'Failed to save',
    ru: 'Не удалось сохранить',
    es: 'Error al guardar',
  },
  'settings.toast.autoGenOn': {
    en: 'Auto-generation on: at most once every {minutes} minutes.',
    ru: 'Автогенерация включена: не чаще одного раза каждые {minutes} минут.',
    es: 'Autogeneración activa: como mucho una vez cada {minutes} minutos.',
  },
  'settings.toast.pipelineCostOptimizedOn': {
    en: 'Optimized token spend enabled',
    ru: 'Оптимизированный расход токенов включён',
    es: 'Gasto de tokens optimizado activado',
  },
  'settings.toast.pipelineCostOptimizedOff': {
    en: 'Optimized token spend disabled (legacy repair budget)',
    ru: 'Оптимизированный расход выключен (legacy бюджет repair)',
    es: 'Gasto optimizado desactivado (presupuesto legacy)',
  },
  'settings.toast.highThroughputOn': {
    en: 'Local high-throughput mode enabled',
    ru: 'Локальный высокопроизводительный режим включён',
    es: 'Modo local de alto rendimiento activado',
  },
  'settings.toast.highThroughputOff': {
    en: 'Local high-throughput mode disabled',
    ru: 'Локальный высокопроизводительный режим выключен',
    es: 'Modo local de alto rendimiento desactivado',
  },
};
