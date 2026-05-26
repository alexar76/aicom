import type { I18nDict } from '../types';

export const PIPELINE_TAB_DICT: I18nDict = {
  'pipeline.title': {
    en: 'Pipeline Monitor',
    ru: 'Монитор пайплайна',
    es: 'Monitor del pipeline',
  },
  'pipeline.updatingServer': {
    en: 'Updating from server…',
    ru: 'Обновление с сервера…',
    es: 'Actualizando desde el servidor…',
  },
  'pipeline.rowsFraction': {
    en: '{loaded} / {total} rows ',
    ru: '{loaded} / {total} строк ',
    es: '{loaded} / {total} filas ',
  },
  'pipeline.ofCatalogLoaded': {
    en: '({pct}% of catalog loaded)',
    ru: '({pct}% каталога загружено)',
    es: '({pct}% del catálogo cargado)',
  },
  'pipeline.loadedTasks.none': {
    en: '0 tasks in loaded rows',
    ru: '0 задач в загруженных строках',
    es: '0 tareas en filas cargadas',
  },
  'pipeline.loadedTasks.line': {
    en: '{total} tasks in loaded rows ({breakdown})',
    ru: '{total} задач в загруженных строках ({breakdown})',
    es: '{total} tareas en filas cargadas ({breakdown})',
  },
  'pipeline.task.running': {
    en: '{n} running',
    ru: '{n} выполняются',
    es: '{n} en ejecución',
  },
  'pipeline.task.pending': {
    en: '{n} pending',
    ru: '{n} в очереди',
    es: '{n} pendientes',
  },
  'pipeline.task.done': {
    en: '{n} done',
    ru: '{n} готово',
    es: '{n} hechas',
  },
  'pipeline.task.failed': {
    en: '{n} failed',
    ru: '{n} с ошибкой',
    es: '{n} fallidas',
  },
  'pipeline.allProductsLoaded': {
    en: 'All {total} products loaded in this view',
    ru: 'Все {total} продуктов загружены в этом виде',
    es: 'Todos los {total} productos cargados en esta vista',
  },
  'pipeline.sortTooltip': {
    en: 'Server-side sort for the whole catalog',
    ru: 'Сортировка на сервере для всего каталога',
    es: 'Orden del lado del servidor para todo el catálogo',
  },
  'pipeline.sortShippedFirst': {
    en: 'Sort: shipped first',
    ru: 'Сортировка: сначала доставленные',
    es: 'Orden: enviados primero',
  },
  'pipeline.sortNewestFirst': {
    en: 'Sort: newest first',
    ru: 'Сортировка: сначала новые',
    es: 'Orden: más nuevos primero',
  },
  'pipeline.allCategories': {
    en: 'All Categories ({count})',
    ru: 'Все категории ({count})',
    es: 'Todas las categorías ({count})',
  },
  'pipeline.catalogBannerTitle': {
    en: 'Catalog vs first rows',
    ru: 'Каталог и первые строки',
    es: 'Catálogo vs primeras filas',
  },
  'pipeline.catalogBannerBody': {
    en:
      'The UI restores the last catalog snapshot from this browser instantly, then revalidates in light mode: first rows for a fast first paint, then batches (no eager per-row spec/marketing disk scan). Rows not yet refreshed this session look slightly muted until live data arrives. Default sort is shipped first so finished builds are not buried under new ideas. Switch to newest first for a strict time line, or use filters (State, Storefront). Public storefront totals use the Dashboard tab.',
    ru:
      'Интерфейс мгновенно восстанавливает последний снимок каталога из браузера, затем подтверждает в лёгком режиме: сначала несколько строк для быстрого первого кадра, затем пакетами (без агрессивного построчного сканирования spec/marketing). Строки, ещё не обновлённые в этой сессии, выглядят чуть тусклее, пока не придут живые данные. По умолчанию сортировка «сначала доставленные», чтобы готовые сборки не утонули под новыми идеями. Переключитесь на «сначала новые» для строгой шкалы времени или используйте фильтры (состояние, витрина). Итоги публичной витрины — на вкладке «Дашборд».',
    es:
      'La UI restaura al instante la última instantánea del catálogo en este navegador y luego revalida en modo ligero: primeras filas para un paint rápido, luego lotes (sin escaneo ansioso fila a fila). Las filas aún no refrescadas se ven algo apagadas hasta que llegan datos en vivo. El orden por defecto es enviados primero para no enterrar builds terminados bajo ideas nuevas. Cambia a más nuevos primero para una línea de tiempo estricta o usa filtros (State, Storefront). Los totales de tienda pública están en Dashboard.',
  },
  'pipeline.stat.inCatalog': {
    en: 'In catalog',
    ru: 'В каталоге',
    es: 'En catálogo',
  },
  'pipeline.stat.shippedState': {
    en: 'Shipped state',
    ru: 'Состояние «доставлено»',
    es: 'Estado enviado',
  },
  'pipeline.stat.publicStorefrontTitle': {
    en: 'Public storefront',
    ru: 'Публичная витрина',
    es: 'Escaparate público',
  },
  'pipeline.stat.needsRework': {
    en: 'Needs rework',
    ru: 'Нужна доработка',
    es: 'Requiere retrabajo',
  },
  'pipeline.dismissNotice': {
    en: 'Dismiss notice',
    ru: 'Скрыть уведомление',
    es: 'Cerrar aviso',
  },
  'pipeline.catalogLoadErrorTitle': {
    en: 'Catalog did not finish loading',
    ru: 'Каталог не загрузился полностью',
    es: 'El catálogo no terminó de cargar',
  },
  'pipeline.catalogLoadErrorBody': {
    en: 'The UI already retried automatically (fast path, then full). If this persists, use Retry — it is usually a temporary API or proxy issue, not an empty pipeline.',
    ru: 'Клиент уже повторил запрос автоматически (быстрый путь и полный). Если не проходит — нажмите «Повторить»: чаще это временная проблема API или прокси, а не пустой пайплайн.',
    es: 'La UI ya reintentó automáticamente (rápido y completo). Si sigue fallando, usa Reintentar: suele ser API o proxy temporal, no un pipeline vacío.',
  },
  'pipeline.retryCatalog': {
    en: 'Retry catalog',
    ru: 'Повторить загрузку каталога',
    es: 'Reintentar catálogo',
  },
  'pipeline.filter.summaryWaitingFirst': {
    en: 'Waiting for the first catalog response (no local snapshot for this sort — see note above the progress bar).',
    ru: 'Ожидание первого ответа каталога (нет локального снимка для этой сортировки — см. подсказку над шкалой).',
    es: 'Esperando la primera respuesta del catálogo (no hay snapshot local para este orden — ver nota sobre la barra).',
  },
  'pipeline.filter.summaryShowing': {
    en: 'Showing {shown} of {loaded} loaded ({catalog} in catalog)',
    ru: 'Показано {shown} из {loaded} загруженных ({catalog} в каталоге)',
    es: 'Mostrando {shown} de {loaded} cargadas ({catalog} en catálogo)',
  },
  'pipeline.search.placeholder': {
    en: 'Search by name, id, description, follow-up…',
    ru: 'Поиск по имени, id, описанию, follow-up…',
    es: 'Buscar por nombre, id, descripción, seguimiento…',
  },
  'pipeline.filter.allStates': {
    en: 'All states',
    ru: 'Все состояния',
    es: 'Todos los estados',
  },
  'pipeline.filter.storefrontAll': {
    en: 'Storefront: all',
    ru: 'Витрина: все',
    es: 'Escaparate: todos',
  },
  'pipeline.filter.storefrontListed': {
    en: 'Storefront: listed',
    ru: 'Витрина: опубликовано',
    es: 'Escaparate: listados',
  },
  'pipeline.filter.storefrontNotListed': {
    en: 'Storefront: not listed',
    ru: 'Витрина: не в списке',
    es: 'Escaparate: sin listar',
  },
  'pipeline.filter.createdFrom': {
    en: 'Created from (local day)',
    ru: 'Создано с (локальный день)',
    es: 'Creado desde (día local)',
  },
  'pipeline.filter.createdTo': {
    en: 'Created to (local day)',
    ru: 'Создано по (локальный день)',
    es: 'Creado hasta (día local)',
  },
  'pipeline.loading.fetchingFirst': {
    en: 'Fetching first catalog page…',
    ru: 'Запрос первой страницы каталога…',
    es: 'Obteniendo la primera página del catálogo…',
  },
  'pipeline.loading.serverRequest': {
    en: 'Server request',
    ru: 'Запрос к серверу',
    es: 'Petición al servidor',
  },
  'pipeline.loading.retryExplainer': {
    en: 'each number is a real HTTP call; if the API is slow or returns an error, the client retries with backoff (this is not a broken connection).',
    ru: 'каждое число — реальный HTTP‑запрос; при медленном API или ошибке клиент повторяет с паузами (это не «разорванное» соединение).',
    es: 'cada número es una llamada HTTP real; si la API va lenta o falla, el cliente reintenta con backoff (no es conexión rota).',
  },
  'pipeline.loading.lastError': {
    en: 'Last error:',
    ru: 'Последняя ошибка:',
    es: 'Último error:',
  },
  'pipeline.loading.nextAttempt': {
    en: 'Next attempt in ~{sec}s',
    ru: 'Следующая попытка через ~{sec} с',
    es: 'Siguiente intento en ~{sec}s',
  },
  'pipeline.loading.browserSnapshotHint': {
    en: 'Browser snapshot:',
    ru: 'Снимок в браузере:',
    es: 'Instantánea del navegador:',
  },
  'pipeline.loading.browserSnapshotTail': {
    en:
      'none for this sort yet — after the first successful load the Pipeline Monitor saves a slim copy in localStorage so the next visit can paint cached rows immediately while refreshing in the background.',
    ru:
      'для этой сортировки пока нет — после успешной первой загрузки Pipeline Monitor сохраняет компактную копию в localStorage, чтобы при следующем визите сразу отрисовать кэш и обновиться в фоне.',
    es:
      'aún no para este orden — tras la primera carga exitosa, Pipeline Monitor guarda una copia en localStorage para pintar filas cacheadas de inicio mientras refresca en segundo plano.',
  },
  'pipeline.loading.footerHint': {
    en:
      'Row-level task counts appear once the first batch returns; the header then shows N / total and the bar below tracks catalog hydration (not this connection phase).',
    ru:
      'Построчные счётчики задач появляются после первой порции данных; затем заголовок показывает N / total, а полоса ниже отражает наполнение каталога (не эту фазу соединения).',
    es:
      'Los conteos de tareas por fila aparecen tras el primer batch; el encabezado muestra N / total y la barra inferior refleja la hidratación del catálogo (no esta fase de conexión).',
  },
  'pipeline.loading.connectionPhase': {
    en: 'Connection phase',
    ru: 'Фаза подключения',
    es: 'Fase de conexión',
  },
  'pipeline.aria.catalogRowsLoaded': {
    en: 'Catalog rows loaded',
    ru: 'Строки каталога загружены',
    es: 'Filas de catálogo cargadas',
  },
  'pipeline.empty.needRetry': {
    en: 'Nothing loaded yet — tap “Retry catalog” above, or open the tab again in a few seconds.',
    ru: 'Пока ничего не загружено — нажмите «Повторить загрузку каталога» выше или откройте вкладку снова через несколько секунд.',
    es: 'Aún no hay datos — usa «Reintentar catálogo» arriba o vuelve a abrir la pestaña en unos segundos.',
  },
  'pipeline.empty.category': {
    en: 'No products in "{category}" category.',
    ru: 'Нет продуктов в категории «{category}».',
    es: 'No hay productos en la categoría "{category}".',
  },
  'pipeline.empty.filtered': {
    en: 'No products match the current filters or search.',
    ru: 'Ничего не подходит под фильтры или поиск.',
    es: 'Ningún producto coincide con filtros o búsqueda.',
  },
  'pipeline.empty.catalog': {
    en: 'No products in the pipeline catalog yet.',
    ru: 'В каталоге пайплайна пока нет продуктов.',
    es: 'Aún no hay productos en el catálogo del pipeline.',
  },
  'pipeline.catalogPublicStoreTooltip': {
    en: 'Products that would appear on the public storefront grid (same rules as /api/products).',
    ru: 'Продукты, которые попали бы на публичную витрину (те же правила, что у /api/products).',
    es: 'Productos que aparecerían en la rejilla pública (mismas reglas que /api/products).',
  },
  'pipeline.modals.loadingSpec': {
    en: 'Loading specification…',
    ru: 'Загрузка спецификации…',
    es: 'Cargando especificación…',
  },
  'pipeline.modals.noSpec': {
    en: 'No specification found for this product.',
    ru: 'Спецификация для этого продукта не найдена.',
    es: 'No se encontró especificación para este producto.',
  },
  'pipeline.modals.loadingDev': {
    en: 'Loading developer inputs…',
    ru: 'Загрузка входных данных разработчика…',
    es: 'Cargando entradas del desarrollador…',
  },
  'pipeline.card.modeProduction': {
    en: 'production',
    ru: 'продакшен',
    es: 'producción',
  },
  'pipeline.card.modePrototype': {
    en: 'prototype',
    ru: 'прототип',
    es: 'prototipo',
  },
  'pipeline.card.spec': { en: 'Spec', ru: 'Спека', es: 'Spec' },
  'pipeline.card.devHandoff': {
    en: 'Dev handoff',
    ru: 'Передача Dev',
    es: 'Entrega a dev',
  },
  'pipeline.card.devHandoffTooltip': {
    en: 'What the Developer agent receives (spec handoff quality)',
    ru: 'Что получает агент Developer (качество передачи спеки)',
    es: 'Qué recibe el agente Developer (calidad del handoff de spec)',
  },
  'pipeline.card.failedBadgeTooltip': {
    en: 'Pipeline paused — use Send to rework below',
    ru: 'Пайплайн на паузе — используйте «Отправить на доработку» ниже',
    es: 'Pipeline en pausa — usa Enviar a retrabajo abajo',
  },
  'pipeline.card.created': {
    en: 'Created {date}',
    ru: 'Создано {date}',
    es: 'Creado {date}',
  },
  'pipeline.vitals.aria': {
    en: 'Product vitals: cost, deadline, quality',
    ru: 'Показатели продукта: затраты, срок, качество',
    es: 'Indicadores: coste, plazo, calidad',
  },
  'pipeline.vitals.costTitle': {
    en: 'LLM spend',
    ru: 'Затраты LLM',
    es: 'Gasto LLM',
  },
  'pipeline.vitals.deadlineTitle': {
    en: 'Timeline',
    ru: 'Срок',
    es: 'Plazo',
  },
  'pipeline.vitals.qualityTitle': {
    en: 'Quality',
    ru: 'Качество',
    es: 'Calidad',
  },
  'pipeline.vitals.costCap': {
    en: 'cap ${cap}',
    ru: 'лимит ${cap}',
    es: 'tope ${cap}',
  },
  'pipeline.vitals.costNoCap': {
    en: 'no per-product cap',
    ru: 'без лимита на продукт',
    es: 'sin tope por producto',
  },
  'pipeline.vitals.costTotal': {
    en: 'Total ${cost}',
    ru: 'Итого ${cost}',
    es: 'Total ${cost}',
  },
  'pipeline.vitals.deadlineDone': {
    en: 'Finished',
    ru: 'Завершён',
    es: 'Terminado',
  },
  'pipeline.vitals.deadlineDoneFailed': {
    en: 'Failed / stopped',
    ru: 'Ошибка / остановлен',
    es: 'Fallido / detenido',
  },
  'pipeline.vitals.deadlineUnknown': {
    en: 'ETA pending',
    ru: 'ETA уточняется',
    es: 'ETA pendiente',
  },
  'pipeline.vitals.qualityUnknown': {
    en: 'Not scored yet',
    ru: 'Оценка ещё не выставлена',
    es: 'Sin puntuación aún',
  },
  'pipeline.economics.llmTooltip': {
    en: 'LLM API cost: {cost} · {calls} calls · {tokens} tokens',
    ru: 'Стоимость LLM API: {cost} · {calls} вызовов · {tokens} токенов',
    es: 'Coste API LLM: {cost} · {calls} llamadas · {tokens} tokens',
  },
  'pipeline.economics.qualityTooltip': {
    en: 'Human quality score (1–5)',
    ru: 'Оценка качества человеком (1–5)',
    es: 'Puntuación humana de calidad (1–5)',
  },
  'pipeline.economics.roiTooltip.green': {
    en: 'Low cost or high quality — good economics',
    ru: 'Низкая стоимость или высокое качество — хорошая экономика',
    es: 'Bajo coste o alta calidad — buena economía',
  },
  'pipeline.economics.roiTooltip.amber': {
    en: 'Moderate cost-to-quality ratio',
    ru: 'Умеренное соотношение цена/качество',
    es: 'Relación moderada coste/calidad',
  },
  'pipeline.economics.roiTooltip.red': {
    en: 'High cost with low quality — needs attention',
    ru: 'Высокая стоимость при низком качестве — нужно внимание',
    es: 'Alto coste con baja calidad — requiere atención',
  },
  'pipeline.economics.roiSuffix': {
    en: ' ROI',
    ru: ' ROI',
    es: ' ROI',
  },
  'pipeline.economics.agentsCount': {
    en: '{n} agents',
    ru: '{n} агентов',
    es: '{n} agentes',
  },
  'pipeline.economics.agentSlice': {
    en: '{agent}: {cost} ({calls} calls, {tokens} tok)',
    ru: '{agent}: {cost} ({calls} вызовов, {tokens} ток)',
    es: '{agent}: {cost} ({calls} llam., {tokens} tok)',
  },
  'pipeline.stageFlow.hint': {
    en: 'Click an agent tile, a colored link between stages, or a task circle below for full task details.',
    ru: 'Нажмите плитку агента, цветную связь между этапами или кружок задачи ниже для подробностей.',
    es: 'Pulsa una ficha de agente, el enlace entre etapas o el círculo de tarea abajo para ver detalles.',
  },
  'pipeline.stage.tileTitle.designer': {
    en: 'Designer (UX): status follows Architect — opens Architect task details',
    ru: 'Designer (UX): статус следует Architect — открывает задачу Architect',
    es: 'Designer (UX): el estado sigue a Architect — abre la tarea de Architect',
  },
  'pipeline.stage.tileTitle.methodologist': {
    en: 'Methodologist: domain methodology snapshot after marketing; backlog for Architect',
    ru: 'Methodologist: снимок доменной методологии после маркетинга; бэклог для Architect',
    es: 'Methodologist: metodología de dominio tras marketing; backlog para Architect',
  },
  'pipeline.stage.tileTitle.default': {
    en: 'Task details for this agent stage',
    ru: 'Подробности задачи для этапа этого агента',
    es: 'Detalles de la tarea de esta etapa',
  },
  'pipeline.stage.abbr.analyst': { en: 'Anl', ru: 'Anl', es: 'Anl' },
  'pipeline.stage.abbr.marketing': { en: 'Mkt', ru: 'Mkt', es: 'Mkt' },
  'pipeline.stage.abbr.designer': { en: 'UX', ru: 'UX', es: 'UX' },
  'pipeline.stage.abbr.methodologist': { en: 'Mth', ru: 'Mth', es: 'Mth' },
  'pipeline.stage.abbr.devops': { en: 'Ops', ru: 'Ops', es: 'Ops' },
  'pipeline.progress.label': { en: 'Progress', ru: 'Прогресс', es: 'Progreso' },
  'pipeline.progress.tasksPct': {
    en: '{done}/{total} tasks ({pct}%)',
    ru: '{done}/{total} задач ({pct}%)',
    es: '{done}/{total} tareas ({pct}%)',
  },
  'pipeline.tasks.summary': {
    en: '{total} tasks ({done} done)',
    ru: '{total} задач ({done} готово)',
    es: '{total} tareas ({done} hechas)',
  },
  'pipeline.tasks.running': {
    en: '{n} running…',
    ru: '{n} выполняются…',
    es: '{n} en ejecución…',
  },
  'pipeline.tasks.rework': {
    en: '{n} rework',
    ru: '{n} доработка',
    es: '{n} retrabajo',
  },
  'pipeline.tasks.show': { en: 'Show Tasks', ru: 'Показать задачи', es: 'Mostrar tareas' },
  'pipeline.tasks.hide': { en: 'Hide Tasks', ru: 'Скрыть задачи', es: 'Ocultar tareas' },
  'pipeline.task.openDetailsTitle': {
    en: 'Open full task details',
    ru: 'Открыть полные детали задачи',
    es: 'Abrir detalles completos de la tarea',
  },
  'pipeline.task.unknownAgent': {
    en: 'Unknown',
    ru: 'Неизвестно',
    es: 'Desconocido',
  },
  'pipeline.task.meta.started': {
    en: 'Started: {time}',
    ru: 'Старт: {time}',
    es: 'Inicio: {time}',
  },
  'pipeline.task.meta.completed': {
    en: 'Completed: {time}',
    ru: 'Завершено: {time}',
    es: 'Completado: {time}',
  },
  'pipeline.task.meta.duration': {
    en: 'Duration: {dur}',
    ru: 'Длительность: {dur}',
    es: 'Duración: {dur}',
  },
  'pipeline.task.meta.llm': {
    en: 'LLM: {sec}s',
    ru: 'LLM: {sec} с',
    es: 'LLM: {sec}s',
  },
  'pipeline.task.stateLabel': {
    en: 'State: {state}',
    ru: 'Состояние: {state}',
    es: 'Estado: {state}',
  },
  'pipeline.syncingCatalog': {
    en: 'Syncing catalog… {loaded} / {total} ({pct}%)',
    ru: 'Синхронизация каталога… {loaded} / {total} ({pct}%)',
    es: 'Sincronizando catálogo… {loaded} / {total} ({pct}%)',
  },
  'pipeline.endOfList': {
    en: 'End of list ({total} products)',
    ru: 'Конец списка ({total} продуктов)',
    es: 'Fin de la lista ({total} productos)',
  },
  'pipeline.modals.specTitle': {
    en: 'Product Specification',
    ru: 'Спецификация продукта',
    es: 'Especificación del producto',
  },
  'pipeline.modals.spec.productName': {
    en: 'Product Name',
    ru: 'Название продукта',
    es: 'Nombre del producto',
  },
  'pipeline.modals.spec.description': {
    en: 'Description',
    ru: 'Описание',
    es: 'Descripción',
  },
  'pipeline.modals.spec.coreFeatures': {
    en: 'Core Features',
    ru: 'Ключевые функции',
    es: 'Funciones clave',
  },
  'pipeline.modals.spec.userStories': {
    en: 'User Stories',
    ru: 'User stories',
    es: 'Historias de usuario',
  },
  'pipeline.modals.spec.technicalRisks': {
    en: 'Technical Risks',
    ru: 'Технические риски',
    es: 'Riesgos técnicos',
  },
  'pipeline.modals.handoffTitle': {
    en: 'Developer handoff (inputs to code agent)',
    ru: 'Передача разработчику (входы для code agent)',
    es: 'Handoff a desarrollo (entradas al agente de código)',
  },
  'pipeline.modals.handoff.product': {
    en: 'Product',
    ru: 'Продукт',
    es: 'Producto',
  },
  'pipeline.modals.handoff.material': {
    en: 'Material: {band}',
    ru: 'Материал: {band}',
    es: 'Material: {band}',
  },
  'pipeline.modals.handoff.warnings': {
    en: 'Warnings',
    ru: 'Предупреждения',
    es: 'Advertencias',
  },
  'pipeline.modals.handoff.adminInstructions': {
    en: 'Admin instructions',
    ru: 'Инструкции админа',
    es: 'Instrucciones de admin',
  },
  'pipeline.modals.handoff.adminEmpty': {
    en: '(empty)',
    ru: '(пусто)',
    es: '(vacío)',
  },
  'pipeline.modals.handoff.analystBrief': {
    en: 'Analyst → developer brief (developer_investigation_brief)',
    ru: 'Analyst → бриф для разработчика (developer_investigation_brief)',
    es: 'Analyst → brief para desarrollo (developer_investigation_brief)',
  },
  'pipeline.modals.handoff.analystBriefEmpty': {
    en: '(empty — for web_app this block is omitted from the developer prompt)',
    ru: '(пусто — для web_app этот блок не попадает в промпт разработчика)',
    es: '(vacío — para web_app este bloque se omite del prompt del desarrollador)',
  },
  'pipeline.modals.handoff.specJson': {
    en: 'Specification (JSON)',
    ru: 'Спецификация (JSON)',
    es: 'Especificación (JSON)',
  },
  'pipeline.modals.handoff.archJson': {
    en: 'Architecture (JSON)',
    ru: 'Архитектура (JSON)',
    es: 'Arquitectura (JSON)',
  },
  'pipeline.modals.handoff.error': {
    en: 'Could not load developer handoff for this product.',
    ru: 'Не удалось загрузить handoff разработчика для этого продукта.',
    es: 'No se pudo cargar el handoff del desarrollador para este producto.',
  },
  'pipeline.modals.task.title': {
    en: '{agent} — pipeline task',
    ru: '{agent} — задача пайплайна',
    es: '{agent} — tarea del pipeline',
  },
  'pipeline.modals.task.designerNote': {
    en:
      'Designer is a pipeline visualization: UX direction is authored with the Architect output (ui_experience). The task record below is the Architect task.',
    ru:
      'Designer — визуализация пайплайна: UX идёт из Architect (ui_experience). Ниже запись задачи Architect.',
    es:
      'Designer es visualización del pipeline: la UX de Architect (ui_experience). El registro abajo es la tarea de Architect.',
  },
  'pipeline.modals.task.noTask': {
    en:
      'No queued task for this stage yet: the pipeline has not reached it, the task was not created, or data is still loading. Expand Show Tasks on the product card below for the full task list.',
    ru:
      'Задачи для этапа пока нет: пайплайн не дошёл, задача не создана или данные ещё грузятся. Разверните «Показать задачи» на карточке для полного списка.',
    es:
      'Aún no hay tarea en cola: el pipeline no llegó, no se creó la tarea o los datos cargan. Expande Mostrar tareas en la tarjeta para la lista completa.',
  },
  'pipeline.modals.task.inferredStage': {
    en:
      'This stage is marked complete from product maturity (40+ finished tasks or shipped state). Historical per-agent rows were compacted during repair loops — expand Show Tasks for the live QA/Dev queue.',
    ru:
      'Этап отмечен выполненным по зрелости продукта (40+ завершённых задач или статус «отгружен»). Старые записи по агентам сжаты в циклах починки — разверните «Показать задачи» для актуальной очереди QA/Dev.',
    es:
      'Etapa marcada completa por madurez del producto (40+ tareas o estado enviado). Filas históricas compactadas en bucles de reparación — expande Mostrar tareas para la cola QA/Dev.',
  },
  'pipeline.modals.task.targetState': {
    en: 'Target pipeline state:',
    ru: 'Целевое состояние пайплайна:',
    es: 'Estado objetivo del pipeline:',
  },
  'pipeline.modals.task.created': { en: 'Created', ru: 'Создано', es: 'Creado' },
  'pipeline.modals.task.started': { en: 'Started', ru: 'Старт', es: 'Inicio' },
  'pipeline.modals.task.completed': {
    en: 'Completed',
    ru: 'Завершено',
    es: 'Completado',
  },
  'pipeline.modals.task.durations': {
    en: 'Durations',
    ru: 'Длительности',
    es: 'Duraciones',
  },
  'pipeline.modals.task.work': {
    en: 'Work: {dur}',
    ru: 'Работа: {dur}',
    es: 'Trabajo: {dur}',
  },
  'pipeline.modals.task.workEmpty': {
    en: 'Work: —',
    ru: 'Работа: —',
    es: 'Trabajo: —',
  },
  'pipeline.modals.task.inQueue': {
    en: 'In queue: {dur}',
    ru: 'В очереди: {dur}',
    es: 'En cola: {dur}',
  },
  'pipeline.modals.task.timeout': {
    en: 'Timeout: {sec}s',
    ru: 'Таймаут: {sec} с',
    es: 'Timeout: {sec}s',
  },
  'pipeline.modals.task.priority': {
    en: 'Priority: {p}',
    ru: 'Приоритет: {p}',
    es: 'Prioridad: {p}',
  },
  'pipeline.modals.task.retries': {
    en: 'Retries: {cur} / {max}',
    ru: 'Повторы: {cur} / {max}',
    es: 'Reintentos: {cur} / {max}',
  },
  'pipeline.modals.task.metrics': {
    en: 'Metrics',
    ru: 'Метрики',
    es: 'Métricas',
  },
  'pipeline.modals.task.critic': {
    en: 'Critic findings',
    ru: 'Замечания критика',
    es: 'Hallazgos del crítico',
  },
  'pipeline.modals.task.inputData': {
    en: 'input_data',
    ru: 'input_data',
    es: 'input_data',
  },
  'pipeline.modals.task.outputData': {
    en: 'output_data',
    ru: 'output_data',
    es: 'output_data',
  },
  'pipeline.modals.task.taskId': {
    en: 'Task ID',
    ru: 'ID задачи',
    es: 'ID de tarea',
  },
  'pipeline.modals.task.productLabel': {
    en: 'Product',
    ru: 'Продукт',
    es: 'Producto',
  },
  'pipeline.task.apiStatus.completed': {
    en: 'completed',
    ru: 'завершено',
    es: 'completada',
  },
  'pipeline.task.apiStatus.running': {
    en: 'running',
    ru: 'выполняется',
    es: 'en ejecución',
  },
  'pipeline.task.apiStatus.failed': {
    en: 'failed',
    ru: 'ошибка',
    es: 'fallida',
  },
  'pipeline.task.apiStatus.pending': {
    en: 'pending',
    ru: 'в очереди',
    es: 'pendiente',
  },
  'pipeline.coach.title': {
    en: 'Pipeline in 60 seconds — no manual required',
    ru: 'Пайплайн за 60 секунд — без руководства',
    es: 'Pipeline en 60 segundos — sin manual',
  },
  'pipeline.coach.step0Prefix': {
    en: 'Step 0: open',
    ru: 'Шаг 0: откройте',
    es: 'Paso 0: abra',
  },
  'pipeline.coach.step0Suffix': {
    en: 'and save one LLM provider — otherwise every agent task will fail.',
    ru: 'и сохраните одного LLM-провайдера — иначе все задачи агентов будут падать.',
    es: 'y guarde un proveedor LLM; si no, todas las tareas de agentes fallarán.',
  },
  'pipeline.coach.step1.label': {
    en: 'Green row',
    ru: 'Зелёная строка',
    es: 'Fila verde',
  },
  'pipeline.coach.step1.rest': {
    en: '= shipped (COMPLETED). Amber = fixing. Red = failed — expand for the error line.',
    ru: '= доставлено (COMPLETED). Янтарная = доработка. Красная = ошибка — разверните строку для текста ошибки.',
    es: '= enviado (COMPLETED). Ámbar = corrección. Roja = fallo — expanda para ver el error.',
  },
  'pipeline.coach.step2.label': {
    en: 'Muted rows',
    ru: 'Тусклые строки',
    es: 'Filas atenuadas',
  },
  'pipeline.coach.step2.rest': {
    en: '= cached snapshot; the bar under the title shows live hydration. Wait for 100% before trusting storefront counts.',
    ru: '= кэшированный снимок; полоса под заголовком показывает живую подгрузку. Дождитесь 100%, прежде чем доверять счётчикам витрины.',
    es: '= instantánea en caché; la barra bajo el título muestra hidratación en vivo. Espere al 100% antes de confiar en los totales de tienda.',
  },
  'pipeline.coach.step3.label': {
    en: 'Queue work',
    ru: 'Поставить в очередь',
    es: 'Encolar trabajo',
  },
  'pipeline.coach.step3.rest': {
    en: '(idea → review → start). Turn on auto-pipeline in Settings if you want a steady stream.',
    ru: '(идея → проверка → старт). Включите авто-пайплайн в «Настройках», если нужен постоянный поток.',
    es: '(idea → revisión → inicio). Active el auto-pipeline en Configuración para un flujo continuo.',
  },
  'pipeline.coach.step4.label': {
    en: 'Stuck?',
    ru: 'Застряли?',
    es: '¿Atascado?',
  },
  'pipeline.coach.step4.prefix': {
    en: 'Check',
    ru: 'Откройте',
    es: 'Abra',
  },
  'pipeline.coach.step4.rest': {
    en: 'and filter State = FAILED here.',
    ru: 'и отфильтруйте здесь State = FAILED.',
    es: 'y filtre aquí State = FAILED.',
  },
  'pipeline.coach.optionalDeepDive': {
    en: 'Optional deep dive',
    ru: 'Подробнее в документации',
    es: 'Profundizar (opcional)',
  },
  'pipeline.coach.dismiss': {
    en: 'Dismiss pipeline coach',
    ru: 'Скрыть подсказку по пайплайну',
    es: 'Ocultar guía del pipeline',
  },
};
