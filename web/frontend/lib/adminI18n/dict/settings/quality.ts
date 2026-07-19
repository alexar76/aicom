import type { I18nDict } from '../../types';

export const QUALITY_SETTINGS_DICT: I18nDict = {
  'settings.quality.title': {
    en: 'Pipeline & product quality',
    ru: 'Качество пайплайна и продукта',
    es: 'Calidad del pipeline y del producto',
  },
  'settings.quality.subtitle': {
    en: 'Tune how strict QA, browser checks, and storefront listing are. Saved with',
    ru: 'Настройте строгость QA, браузерных проверок и публикации на витрине. Сохраняется с',
    es: 'Ajusta la rigurosidad de QA, comprobaciones en navegador y listado en vitrina. Se guarda con',
  },
  'settings.quality.subtitleSave': {
    en: 'Save settings',
    ru: '«Сохранить настройки»',
    es: '«Guardar ajustes»',
  },
  'settings.quality.intro': {
    en: 'Values are stored in platform config under quality:. If your deployment sets matching AIFACTORY_* environment variables, those still win for operators who need a hard override in Docker.',
    ru: 'Значения хранятся в конфиге платформы в quality:. Если в деплое заданы соответствующие переменные AIFACTORY_*, они имеют приоритет для жёсткого override в Docker.',
    es: 'Los valores se guardan en la config de la plataforma en quality:. Si el despliegue define variables AIFACTORY_* coincidentes, siguen teniendo prioridad para override en Docker.',
  },
  'settings.quality.section.repair': {
    en: 'Repair budget & LLM spend',
    ru: 'Бюджет доработок и затраты LLM',
    es: 'Presupuesto de reparación y gasto LLM',
  },
  'settings.quality.maxPipelineCost.label': {
    en: 'Max LLM cost per product (USD)',
    ru: 'Макс. стоимость LLM на продукт (USD)',
    es: 'Coste LLM máx. por producto (USD)',
  },
  'settings.quality.maxPipelineCost.desc': {
    en: '0 = unlimited. When set, the pipeline aborts agent tasks once estimated LLM spend (llm_calls.jsonl) exceeds this cap. Env AIFACTORY_MAX_PIPELINE_COST_USD overrides this field when set.',
    ru: '0 = без лимита. При значении > 0 пайплайн останавливает задачи агентов, когда оценочные затраты LLM (llm_calls.jsonl) превышают лимит. Переменная AIFACTORY_MAX_PIPELINE_COST_USD имеет приоритет над полем.',
    es: '0 = sin límite. Si es > 0, el pipeline detiene tareas cuando el gasto LLM estimado (llm_calls.jsonl) supera el tope. La variable AIFACTORY_MAX_PIPELINE_COST_USD tiene prioridad sobre este campo.',
  },
  'settings.quality.maxRepair.label': {
    en: 'Max quality repair rounds',
    ru: 'Макс. раундов quality-repair',
    es: 'Máx. rondas de reparación de calidad',
  },
  'settings.quality.maxRepair.desc': {
    en: 'How many times the pipeline can send a product back to Development after QA or marketplace checks fail before the product is marked failed. Higher is more forgiving; lower fails faster.',
    ru: 'Сколько раз пайплайн может вернуть продукт в Development после сбоев QA или витрины, прежде чем продукт помечается failed. Больше — мягче; меньше — быстрее fail.',
    es: 'Cuántas veces el pipeline puede devolver un producto a Development tras fallos de QA o vitrina antes de marcarlo failed. Más alto = más indulgente.',
  },
  'settings.quality.maxRepairLanding.label': {
    en: 'Max repair rounds (marketing landings)',
    ru: 'Макс. раундов repair (marketing landing)',
    es: 'Máx. rondas repair (landings)',
  },
  'settings.quality.maxRepairLanding.desc': {
    en: 'Lower cap for brochure-only builds so landings ship instead of burning tokens in long QA ping-pong. Never above the global max above.',
    ru: 'Нижний лимит для brochure-only, чтобы лендинги шипились, а не жгли токены в длинном QA. Не выше глобального максимума.',
    es: 'Tope más bajo para landings brochure-only para que envíen sin quemar tokens en QA largo. Nunca por encima del máximo global.',
  },
  'settings.quality.section.postShip': {
    en: 'Post-ship improvement',
    ru: 'Улучшение после ship',
    es: 'Mejora post-ship',
  },
  'settings.quality.monitoringDevRefresh.label': {
    en: 'Analyst monitoring → full dev regen',
    ru: 'Мониторинг analyst → полный dev regen',
    es: 'Monitoreo analyst → regen completo dev',
  },
  'settings.quality.monitoringDevRefresh.desc': {
    en: 'When on, daily analyst monitoring on COMPLETED products can queue expensive developer+QA repair cycles. Off = analyst still runs; no automatic regen (recommended in optimized mode).',
    ru: 'Если вкл., ежедневный analyst на COMPLETED может ставить дорогие циклы developer+QA. Выкл. = analyst работает, но без автоматического regen (рекомендуется в optimized).',
    es: 'Si está activo, el analyst diario en COMPLETED puede encolar ciclos caros developer+QA. Desactivado = analyst sigue, sin regen automático (recomendado en modo optimizado).',
  },
  'settings.quality.section.demo': {
    en: 'Demo & static QA',
    ru: 'Демо и статический QA',
    es: 'Demo y QA estático',
  },
  'settings.quality.demoMin.label': {
    en: 'Minimum demo quality score',
    ru: 'Минимальный балл demo quality',
    es: 'Puntuación mínima de calidad demo',
  },
  'settings.quality.demoMin.desc': {
    en: 'Score (0–100) from the static demo audit. Below this, QA does not let the product advance toward security.',
    ru: 'Балл (0–100) статического demo-аудита. Ниже — QA не пускает продукт к security.',
    es: 'Puntuación (0–100) del auditoría demo estática. Por debajo, QA no deja avanzar hacia security.',
  },
  'settings.quality.strictDemo.label': {
    en: 'Strict demo gates',
    ru: 'Строгие demo-гейты',
    es: 'Gates demo estrictos',
  },
  'settings.quality.strictDemo.desc': {
    en: 'When on, additional HTML/link issues (e.g. broken internal links, very thin pages) fail QA even if the headline score is above the minimum.',
    ru: 'При включении дополнительные проблемы HTML/ссылок (битые внутренние ссылки, тонкие страницы) валят QA даже при балле выше минимума.',
    es: 'Si está activo, problemas HTML/enlaces adicionales fallan QA aunque la puntuación supere el mínimo.',
  },
  'settings.quality.section.visual': {
    en: 'Visual heuristics',
    ru: 'Визуальные эвристики',
    es: 'Heurísticas visuales',
  },
  'settings.quality.visualRun.label': {
    en: 'Run visual checks',
    ru: 'Запускать визуальные проверки',
    es: 'Ejecutar comprobaciones visuales',
  },
  'settings.quality.visualRun.desc': {
    en: 'Static heuristics on HTML/CSS (tokens, skeleton states, basic a11y hints). Usually leave on.',
    ru: 'Статические эвристики HTML/CSS (токены, skeleton, базовая a11y). Обычно оставляют включёнными.',
    es: 'Heurísticas estáticas en HTML/CSS (tokens, skeleton, pistas a11y). Suele dejarse activo.',
  },
  'settings.quality.visualStrict.label': {
    en: 'Strict visual mode',
    ru: 'Строгий визуальный режим',
    es: 'Modo visual estricto',
  },
  'settings.quality.visualStrict.desc': {
    en: 'When on, a defined set of visual issue codes fails the gate outright (stricter than headline score alone).',
    ru: 'При включении заданный набор кодов визуальных проблем сразу валит гейт (строже, чем только итоговый балл).',
    es: 'Si está activo, un conjunto de códigos visuales falla el gate de inmediato (más estricto que la puntuación global).',
  },
  'settings.quality.visualApp.label': {
    en: 'App-like surface checks',
    ru: 'Проверки «как у приложения»',
    es: 'Comprobaciones tipo app',
  },
  'settings.quality.visualApp.desc': {
    en: 'For dashboard / full-software style specs, require skeleton, empty, and error UI patterns. Turn off only for pure marketing landings if false positives annoy you.',
    ru: 'Для dashboard / full-software требуются skeleton, empty и error UI. Отключайте только для чистых лендингов при ложных срабатываниях.',
    es: 'Para specs tipo dashboard/full-software exige patrones skeleton, empty y error UI. Desactiva solo en landings puros si hay falsos positivos.',
  },
  'settings.quality.section.browser': {
    en: 'Browser QA (Playwright)',
    ru: 'Браузерный QA (Playwright)',
    es: 'QA en navegador (Playwright)',
  },
  'settings.quality.browserE2e.label': {
    en: 'Run browser E2E during QA',
    ru: 'E2E в браузере во время QA',
    es: 'E2E en navegador durante QA',
  },
  'settings.quality.browserE2e.desc': {
    en: 'Headless Chromium crawl of the generated site. Disabling speeds QA up but skips realistic navigation checks.',
    ru: 'Headless Chromium по сгенерированному сайту. Отключение ускоряет QA, но пропускает реалистичную навигацию.',
    es: 'Rastreo Chromium headless del sitio generado. Desactivar acelera QA pero omite comprobaciones realistas.',
  },
  'settings.quality.browserPages.label': {
    en: 'Max pages per crawl',
    ru: 'Макс. страниц за обход',
    es: 'Máx. páginas por rastreo',
  },
  'settings.quality.browserPages.desc': {
    en: 'Safety cap on how many distinct URLs the deep crawl visits. Raise for large sites; lower for faster CI.',
    ru: 'Лимит уникальных URL при глубоком обходе. Выше — для больших сайтов; ниже — для быстрого CI.',
    es: 'Tope de URLs distintas en el rastreo profundo. Sube para sitios grandes; baja para CI rápido.',
  },
  'settings.quality.browserDepth.label': {
    en: 'Max crawl depth',
    ru: 'Макс. глубина обхода',
    es: 'Profundidad máxima de rastreo',
  },
  'settings.quality.browserDepth.desc': {
    en: 'Maximum link depth from the start page. Deeper finds more issues but takes longer.',
    ru: 'Максимальная глубина ссылок от стартовой страницы. Глубже — больше находок, дольше по времени.',
    es: 'Profundidad máxima de enlaces desde la página inicial. Más profundo encuentra más, pero tarda más.',
  },
  'settings.quality.section.storefront': {
    en: 'Public storefront listing',
    ru: 'Публикация на публичной витрине',
    es: 'Listado en vitrina pública',
  },
  'settings.quality.marketGate.label': {
    en: 'Enable listing quality gate',
    ru: 'Включить гейт качества для витрины',
    es: 'Activar gate de calidad de listado',
  },
  'settings.quality.marketGate.desc': {
    en: 'When off, every completed product can appear on the public grid (debug only). When on, products must pass the rules below.',
    ru: 'Выкл.: любой completed продукт на публичной сетке (только отладка). Вкл.: нужны правила ниже.',
    es: 'Apagado: todo producto completed en la rejilla (solo debug). Encendido: deben pasar las reglas siguientes.',
  },
  'settings.quality.fullQa.label': {
    en: 'Require full QA telemetry',
    ru: 'Требовать полную телеметрию QA',
    es: 'Exigir telemetría QA completa',
  },
  'settings.quality.fullQa.desc': {
    en: 'Require saved browser/QA telemetry with all gates passed before a product may be listed.',
    ru: 'Требовать сохранённую браузерную/QA телеметрию со всеми пройденными гейтами перед листингом.',
    es: 'Exige telemetría browser/QA guardada con todos los gates pasados antes de listar.',
  },
  'settings.quality.specCoverage.label': {
    en: 'Minimum spec keyword coverage (%)',
    ru: 'Мин. покрытие ключевых слов спеки (%)',
    es: 'Cobertura mínima de keywords de spec (%)',
  },
  'settings.quality.specCoverage.desc': {
    en: 'When the spec defines measurable keywords, listing requires at least this coverage. Set to 0 to disable this check.',
    ru: 'Если в спеке заданы измеримые ключевые слова, для листинга нужно не меньше этого %. 0 — отключить проверку.',
    es: 'Si la spec define keywords medibles, el listado exige al menos esta cobertura. 0 desactiva la comprobación.',
  },
  'settings.quality.designNoveltyReq.label': {
    en: 'Require architecture novelty',
    ru: 'Требовать новизну архитектуры',
    es: 'Exigir novedad de arquitectura',
  },
  'settings.quality.designNoveltyReq.desc': {
    en: 'When an architecture novelty score exists, it must meet the minimum below.',
    ru: 'Если есть балл новизны архитектуры, он должен быть не ниже минимума ниже.',
    es: 'Si existe puntuación de novedad arquitectónica, debe cumplir el mínimo inferior.',
  },
  'settings.quality.designNoveltyMin.label': {
    en: 'Minimum design novelty score',
    ru: 'Минимальный балл новизны дизайна',
    es: 'Puntuación mínima de novedad de diseño',
  },
  'settings.quality.designNoveltyMin.desc': {
    en: 'Threshold for architecture novelty (0–1). Only used when a score is present and the requirement above is on.',
    ru: 'Порог новизны архитектуры (0–1). Только если балл есть и требование выше включено.',
    es: 'Umbral de novedad (0–1). Solo si hay puntuación y el requisito superior está activo.',
  },
  'settings.quality.qaRealism.label': {
    en: 'Block high-severity QA realism findings',
    ru: 'Блокировать серьёзные QA realism-находки',
    es: 'Bloquear hallazgos QA realism graves',
  },
  'settings.quality.qaRealism.desc': {
    en: 'When on, backend realism issues reported by QA can block storefront listing.',
    ru: 'При включении проблемы backend realism от QA могут блокировать листинг на витрине.',
    es: 'Si está activo, problemas de realism del backend reportados por QA pueden bloquear el listado.',
  },
  'settings.quality.releaseScoreReq.label': {
    en: 'Require release score from QA',
    ru: 'Требовать release score от QA',
    es: 'Exigir release score de QA',
  },
  'settings.quality.releaseScoreReq.desc': {
    en: 'When the QA report includes a release score, it must meet the minimum below.',
    ru: 'Если в отчёте QA есть release score, он должен быть не ниже минимума ниже.',
    es: 'Si el informe QA incluye release score, debe cumplir el mínimo inferior.',
  },
  'settings.quality.releaseScoreMin.label': {
    en: 'Minimum release score',
    ru: 'Минимальный release score',
    es: 'Release score mínimo',
  },
  'settings.quality.releaseScoreMin.desc': {
    en: '0–100; used only when a release score exists and the requirement above is enabled.',
    ru: '0–100; только если release score есть и требование выше включено.',
    es: '0–100; solo si existe release score y el requisito superior está activo.',
  },
  'settings.quality.placeholderName.label': {
    en: 'Reject placeholder product names',
    ru: 'Отклонять placeholder-имена продуктов',
    es: 'Rechazar nombres placeholder',
  },
  'settings.quality.placeholderName.desc': {
    en: 'Blocks obviously generic or spam titles from being listed.',
    ru: 'Блокирует явно generic или спамные названия при листинге.',
    es: 'Bloquea títulos obviamente genéricos o spam en el listado.',
  },
  'settings.quality.methodology.label': {
    en: 'Require methodology review',
    ru: 'Требовать methodology review',
    es: 'Exigir revisión de metodología',
  },
  'settings.quality.methodology.desc': {
    en: 'Listing may require methodology pack / review signals to be satisfied.',
    ru: 'Листинг может требовать выполнения сигналов methodology pack / review.',
    es: 'El listado puede exigir señales de paquete/revisión metodológica.',
  },
  'settings.quality.constitutionListing.label': {
    en: 'Require quality constitution (listing)',
    ru: 'Требовать quality constitution (листинг)',
    es: 'Exigir constitución de calidad (listado)',
  },
  'settings.quality.constitutionListing.desc': {
    en: 'Runs the quality constitution gate before allowing listing (stricter orgs).',
    ru: 'Запускает гейт quality constitution перед листингом (строже для организаций).',
    es: 'Ejecuta el gate de constitución de calidad antes del listado (organizaciones estrictas).',
  },
  'settings.quality.releaseCockpit.label': {
    en: 'Require release cockpit “go”',
    ru: 'Требовать «go» release cockpit',
    es: 'Exigir «go» del release cockpit',
  },
  'settings.quality.releaseCockpit.desc': {
    en: 'When on, the release cockpit must report go before listing.',
    ru: 'При включении release cockpit должен дать go перед листингом.',
    es: 'Si está activo, el release cockpit debe reportar go antes del listado.',
  },
  'settings.quality.section.constitution': {
    en: 'Pipeline constitution',
    ru: 'Конституция пайплайна',
    es: 'Constitución del pipeline',
  },
  'settings.quality.constitutionPipeline.label': {
    en: 'Quality constitution during pipeline',
    ru: 'Quality constitution во время пайплайна',
    es: 'Constitución de calidad durante el pipeline',
  },
  'settings.quality.constitutionPipeline.desc': {
    en: 'When on, runtime guards may attach constitution-based issues before certain stages complete. Disable only for debugging.',
    ru: 'При включении runtime guards могут добавлять issues по конституции до завершения стадий. Отключайте только для отладки.',
    es: 'Si está activo, los guards en runtime pueden adjuntar issues de constitución antes de ciertas etapas. Solo desactivar para depurar.',
  },
};
