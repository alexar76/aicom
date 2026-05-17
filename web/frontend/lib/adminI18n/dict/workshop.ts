import type { I18nDict } from '../types';

export const WORKSHOP_DICT: I18nDict = {
  'workshop.title': {
    en: 'Product Workshop',
    ru: 'Мастерская продуктов',
    es: 'Taller de productos',
  },
  'workshop.subtitle': {
    en: 'Board of recent products, specification and architecture JSON diffs, a lightweight iteration canvas (branches + merge edges), synchronized iframe previews for a multi-device lab, cloud pattern library, and admin Web Push.',
    ru: 'Доска недавних продуктов, диффы JSON спецификации и архитектуры, облегчённый canvas итераций (ветки + рёбра слияния), синхронные iframe‑предпросмотры для многоплатформенной лаборатории, облачная библиотека паттернов и Web Push для админки.',
    es: 'Tablero de productos recientes, diffs JSON de especificación y arquitectura, lienzo ligero de iteración (ramas + aristas de merge), vistas iframe sincronizadas para un laboratorio multidispositivo, biblioteca de patrones en la nube y Web Push de administración.',
  },
  'workshop.intro.title': {
    en: 'How to use this tab',
    ru: 'Как пользоваться вкладкой',
    es: 'Cómo usar esta pestaña',
  },
  'workshop.intro.li1': {
    en: 'Pick product IDs from the board (or paste from Pipeline), then load spec or architecture JSON.',
    ru: 'Выберите ID продуктов на доске (или скопируйте из Pipeline), затем загрузите JSON спецификации или архитектуры.',
    es: 'Elige IDs en el tablero (o pégalo desde Pipeline) y luego carga JSON de spec o arquitectura.',
  },
  'workshop.intro.li2': {
    en: 'Iteration canvas persists per product — load after pressing "Use ID" on a card.',
    ru: 'Canvas итераций хранится на продукт — загрузите после «Использовать ID» на карточке.',
    es: 'El lienzo de iteración persiste por producto — cárgalo tras pulsar «Usar ID» en una tarjeta.',
  },
  'workshop.intro.li3': {
    en: 'When something fails, use the red action card: retry plus deep links (Providers, Settings, Pipeline).',
    ru: 'При ошибках используйте красную карточку: повтор и глубокие ссылки (Провайдеры, Настройки, Пайплайн).',
    es: 'Si falla algo, usa la tarjeta roja de acción: reintento y enlaces (Providers, Settings, Pipeline).',
  },
  'workshop.intro.dismissAria': {
    en: 'Dismiss workshop tips',
    ru: 'Скрыть подсказки мастерской',
    es: 'Cerrar consejos del taller',
  },
  'workshop.board.title': {
    en: 'Board',
    ru: 'Доска',
    es: 'Tablero',
  },
  'workshop.board.refresh': { en: 'Refresh', ru: 'Обновить', es: 'Actualizar' },
  'workshop.board.loading': {
    en: 'Loading recent products…',
    ru: 'Загрузка недавних продуктов…',
    es: 'Cargando productos recientes…',
  },
  'workshop.board.retryLabel': {
    en: 'Reload board',
    ru: 'Перезагрузить доску',
    es: 'Recargar tablero',
  },
  'workshop.board.empty.title': {
    en: 'No products in this catalog slice yet.',
    ru: 'В этом срезе каталога пока нет продуктов.',
    es: 'Aún no hay productos en este corte del catálogo.',
  },
  'workshop.board.empty.body': {
    en: 'Create one under ',
    ru: 'Создайте в ',
    es: 'Crea uno en ',
  },
  'workshop.board.empty.newProduct': {
    en: 'New product',
    ru: 'Новый продукт',
    es: 'Nuevo producto',
  },
  'workshop.board.empty.orOpen': {
    en: ', or open ',
    ru: ', либо откройте ',
    es: ', o abre ',
  },
  'workshop.board.empty.pipeline': {
    en: 'Pipeline',
    ru: 'Пайплайн',
    es: 'Pipeline',
  },
  'workshop.board.empty.tail': {
    en: ' if the list should already contain items (check filters / worker).',
    ru: ', если записи уже должны быть (проверьте фильтры / воркер).',
    es: ' si la lista ya debería tener datos (revisa filtros / worker).',
  },
  'workshop.board.storeUrl': {
    en: 'Store URL',
    ru: 'URL витрины',
    es: 'URL de tienda',
  },
  'workshop.board.open': { en: 'Open', ru: 'Открыть', es: 'Abrir' },
  'workshop.board.useId': { en: 'Use ID', ru: 'Использовать ID', es: 'Usar ID' },
  'workshop.diff.title': {
    en: 'Side-by-side material diff',
    ru: 'Сравнение материалов рядом',
    es: 'Diff lado a lado del material',
  },
  'workshop.diff.hint': {
    en: 'Choose specification.json or on-disk architecture.json for both products.',
    ru: 'Выберите specification.json или файл architecture.json для обоих продуктов.',
    es: 'Elige specification.json o architecture.json en disco para ambos productos.',
  },
  'workshop.diff.spec': {
    en: 'Specification',
    ru: 'Спецификация',
    es: 'Especificación',
  },
  'workshop.diff.architecture': {
    en: 'Architecture',
    ru: 'Архитектура',
    es: 'Arquitectura',
  },
  'workshop.diff.productA': { en: 'Product A', ru: 'Продукт A', es: 'Producto A' },
  'workshop.diff.productB': { en: 'Product B', ru: 'Продукт B', es: 'Producto B' },
  'workshop.diff.select': { en: 'Select…', ru: 'Выберите…', es: 'Seleccionar…' },
  'workshop.diff.loadJson': {
    en: 'Load JSON',
    ru: 'Загрузить JSON',
    es: 'Cargar JSON',
  },
  'workshop.diff.retryLoad': {
    en: 'Retry JSON load',
    ru: 'Повторить загрузку JSON',
    es: 'Reintentar carga JSON',
  },
  'workshop.toast.pickTwoProducts': {
    en: 'Pick two different product IDs',
    ru: 'Выберите два разных ID продукта',
    es: 'Elige dos IDs de producto distintos',
  },
  'workshop.toast.copied': { en: 'Copied', ru: 'Скопировано', es: 'Copiado' },
  'workshop.toast.copyFailed': {
    en: 'Copy failed',
    ru: 'Не удалось скопировать',
    es: 'Error al copiar',
  },
  'workshop.invalidJson.title': {
    en: 'Invalid JSON',
    ru: 'Некорректный JSON',
    es: 'JSON no válido',
  },
  'workshop.invalidJson.detail': {
    en: 'Fix the pattern document before saving.',
    ru: 'Исправьте документ паттерна перед сохранением.',
    es: 'Corrige el documento del patrón antes de guardar.',
  },
  'workshop.pattern.saved': {
    en: 'Pattern saved',
    ru: 'Паттерн сохранён',
    es: 'Patrón guardado',
  },
  'workshop.pattern.deleted': {
    en: 'Deleted',
    ru: 'Удалено',
    es: 'Eliminado',
  },
  'workshop.canvas.title': {
    en: 'Iteration canvas (branches / merge)',
    ru: 'Canvas итераций (ветки / слияние)',
    es: 'Lienzo de iteración (ramas / merge)',
  },
  'workshop.canvas.hint': {
    en: 'Persisted per product. Drag nodes, fork a node onto a new branch id, and record merge edges. Full Miro-style CRDT sync is not included — this board is for workshop notes tied to pipeline IDs.',
    ru: 'Хранится на продукт. Перетаскивайте узлы, ответвляйте на новый id ветки, фиксируйте рёбра слияния. Полная CRDT‑синхронизация в стиле Miro отсутствует — это доска заметок, привязанная к ID пайплайна.',
    es: 'Persistente por producto. Arrastra nodos, bifurca a un nuevo id de rama y registra merges. No hay sync CRDT estilo Miro: es una pizarra de taller ligada a IDs del pipeline.',
  },
  'workshop.canvas.productIdLabel': {
    en: 'Product ID',
    ru: 'ID продукта',
    es: 'ID de producto',
  },
  'workshop.placeholder.productId': {
    en: 'prod-…',
    ru: 'prod-…',
    es: 'prod-…',
  },
  'workshop.placeholder.sandboxId': {
    en: 'sandbox-…',
    ru: 'sandbox-…',
    es: 'sandbox-…',
  },
  'workshop.canvas.load': { en: 'Load', ru: 'Загрузить', es: 'Cargar' },
  'workshop.canvas.save': { en: 'Save', ru: 'Сохранить', es: 'Guardar' },
  'workshop.canvas.addStage': {
    en: 'Add stage',
    ru: 'Добавить этап',
    es: 'Añadir etapa',
  },
  'workshop.canvas.retryLoadCanvas': {
    en: 'Retry load canvas',
    ru: 'Повторить загрузку canvas',
    es: 'Reintentar carga del lienzo',
  },
  'workshop.canvas.retrySaveCanvas': {
    en: 'Retry save canvas',
    ru: 'Повторить сохранение canvas',
    es: 'Reintentar guardar lienzo',
  },
  'workshop.edgeHelpers.label': {
    en: 'Fork / merge helpers:',
    ru: 'Помощники ветки / слияния:',
    es: 'Ayudas de fork / merge:',
  },
  'workshop.edge.fromNode': {
    en: 'From node…',
    ru: 'Из узла…',
    es: 'Desde nodo…',
  },
  'workshop.edge.toNode': {
    en: 'To node…',
    ru: 'В узел…',
    es: 'Hacia nodo…',
  },
  'workshop.edge.link': {
    en: 'Link',
    ru: 'Связать',
    es: 'Enlazar',
  },
  'workshop.edge.merge': {
    en: 'Merge edge',
    ru: 'Ребро слияния',
    es: 'Arista de merge',
  },
  'workshop.edge.forkFrom': {
    en: 'Fork «from»',
    ru: 'Ветка от «из»',
    es: 'Bifurcar «desde»',
  },
  'workshop.lab.title': {
    en: 'Multi-device lab · live-ish preview',
    ru: 'Мульти‑устройство · живой предпросмотр',
    es: 'Laboratorio multidispositivo · vista casi en vivo',
  },
  'workshop.lab.hint': {
    en: 'Three iframes load the same sandbox viewer URL and refresh on an interval (simulates multiple clients). True WebRTC or screen streaming needs a dedicated signaling service — not bundled here.',
    ru: 'Три iframe загружают один и тот же URL просмотра песочницы и обновляются по интервалу (имитация клиентов). Настоящий WebRTC или стрим экрана требует отдельный сигналинг — здесь не включён.',
    es: 'Tres iframes cargan la misma URL del visor y se refrescan en intervalos (simula varios clientes). WebRTC o streaming real requiere señalización dedicada — no incluido.',
  },
  'workshop.lab.productIdAnnot': {
    en: 'Product ID (annotation only)',
    ru: 'ID продукта (только подпись)',
    es: 'ID de producto (solo anotación)',
  },
  'workshop.lab.sandboxId': {
    en: 'Sandbox ID',
    ru: 'ID песочницы',
    es: 'ID de sandbox',
  },
  'workshop.lab.refreshMs': {
    en: 'Refresh interval (ms)',
    ru: 'Интервал обновления (мс)',
    es: 'Intervalo de refresco (ms)',
  },
  'workshop.lab.deviceN': {
    en: 'Device {n}',
    ru: 'Устройство {n}',
    es: 'Dispositivo {n}',
  },
  'workshop.lab.enterSandboxHint': {
    en: 'Enter a sandbox id from Pipeline / sandbox start to render previews.',
    ru: 'Введите ID песочницы из Pipeline / запуска sandbox, чтобы показать превью.',
    es: 'Introduce un id de sandbox desde Pipeline / inicio de sandbox para previsualizar.',
  },
  'workshop.patterns.title': {
    en: 'Cloud pattern library',
    ru: 'Облачная библиотека паттернов',
    es: 'Biblioteca de patrones en la nube',
  },
  'workshop.patterns.hint': {
    en: 'JSON documents stored on the server (same factory data directory as templates). Use for reusable workshop shapes, checklists, or iteration recipes beyond reference templates.',
    ru: 'Документы JSON на сервере (тот же каталог данных, что у шаблонов). Для повторно используемых форм, чек‑листов или рецептов итераций поверх reference templates.',
    es: 'Documentos JSON en el servidor (mismo directorio de datos que plantillas). Para formas reutilizables, listas o recetas de iteración más allá de reference templates.',
  },
  'workshop.patterns.namePlaceholder': {
    en: 'Pattern name',
    ru: 'Имя паттерна',
    es: 'Nombre del patrón',
  },
  'workshop.patterns.tagsPlaceholder': {
    en: 'tags, comma-separated',
    ru: 'теги через запятую',
    es: 'etiquetas, separadas por coma',
  },
  'workshop.patterns.save': {
    en: 'Save pattern',
    ru: 'Сохранить паттерн',
    es: 'Guardar patrón',
  },
  'workshop.patterns.reloadList': {
    en: 'Reload list',
    ru: 'Обновить список',
    es: 'Recargar lista',
  },
  'workshop.patterns.reloadRetry': {
    en: 'Reload patterns',
    ru: 'Перезагрузить паттерны',
    es: 'Recargar patrones',
  },
  'workshop.patterns.delete': {
    en: 'Delete',
    ru: 'Удалить',
    es: 'Eliminar',
  },
  'workshop.push.title': {
    en: 'Web Push (this browser)',
    ru: 'Web Push (этот браузер)',
    es: 'Web Push (este navegador)',
  },
  'workshop.push.hint': {
    en: 'Uses the existing /sw.js worker (push handler). After subscribing, use “Send test” — payloads also fire after successful Telegram pipeline notifications when subscriptions exist.',
    ru: 'Используется существующий /sw.js (обработчик push). После подписки — «Тестовая отправка»; уведомления также уходят после успешных Telegram‑оповещений пайплайна при наличии подписок.',
    es: 'Usa el worker /sw.js existente. Tras suscribirte, usa «Enviar prueba»; los payloads también se envían tras notificaciones Telegram exitosas del pipeline si hay suscripciones.',
  },
  'workshop.push.subscribe': {
    en: 'Subscribe',
    ru: 'Подписаться',
    es: 'Suscribirse',
  },
  'workshop.push.sendTest': {
    en: 'Send test push',
    ru: 'Тестовый push',
    es: 'Enviar push de prueba',
  },
  'workshop.push.retrySubscribe': {
    en: 'Retry subscribe',
    ru: 'Повторить подписку',
    es: 'Reintentar suscripción',
  },
  'workshop.push.retryTest': {
    en: 'Retry test push',
    ru: 'Повторить тестовый push',
    es: 'Reintentar push de prueba',
  },
  'workshop.push.notSupported': {
    en: 'Push not supported in this browser',
    ru: 'Push не поддерживается в этом браузере',
    es: 'Push no compatible en este navegador',
  },
  'workshop.push.subscribed': {
    en: 'Subscribed to Web Push on this browser',
    ru: 'Подписка на Web Push в этом браузере оформлена',
    es: 'Suscrito a Web Push en este navegador',
  },
  'workshop.push.testTitle': {
    en: 'AI Factory test',
    ru: 'Тест AI Factory',
    es: 'Prueba AI Factory',
  },
  'workshop.push.testBody': {
    en: 'If you see this, Web Push delivery works.',
    ru: 'Если видите это, доставка Web Push работает.',
    es: 'Si ves esto, la entrega Web Push funciona.',
  },
  'workshop.pattern.untitled': {
    en: 'Untitled pattern',
    ru: 'Безымянный паттерн',
    es: 'Patrón sin título',
  },
  'workshop.push.testToast': {
    en: 'Sent: {sent}, failed: {failed}{errorPart}',
    ru: 'Отправлено: {sent}, ошибок: {failed}{errorPart}',
    es: 'Enviados: {sent}, fallidos: {failed}{errorPart}',
  },
  'workshop.diff.emptyPlaceholder': {
    en: '—',
    ru: '—',
    es: '—',
  },
  'workshop.diff.panelCaption': {
    en: '{side} · {id} · {kind}',
    ru: '{side} · {id} · {kind}',
    es: '{side} · {id} · {kind}',
  },
};
