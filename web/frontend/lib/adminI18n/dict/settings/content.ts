import type { I18nDict } from '../../types';

export const CONTENT_SETTINGS_DICT: I18nDict = {
  'settings.section.neuralUi': {
    en: 'Neural UI reference pool',
    ru: 'Пул Neural UI‑референсов',
    es: 'Pool de referencias Neural UI',
  },
  'settings.neuralUi.intro': {
    en: 'Optionally inject a generated vanilla HTML/CSS/JS shell into the Developer (and Hardening) prompt so new products mirror motion, tokens, and layout polish. Build the pool offline: python scripts/generate_reference_templates.py --data-root ./data — outputs under data/reference_templates/ plus manifest.json. Style presets live in reference_templates/style_presets.json. Environment variables AIFACTORY_REFERENCE_* override these saved values on the worker.',
    ru: 'По желанию вставляйте сгенерированную оболочку HTML/CSS/JS без фреймворков в промпт Developer (и Hardening), чтобы новые продукты повторяли motion, токены и вёрстку. Соберите пул офлайн: python scripts/generate_reference_templates.py --data-root ./data — вывод в data/reference_templates/ и manifest.json. Стилевые пресеты: reference_templates/style_presets.json. Переменные AIFACTORY_REFERENCE_* в env переопределяют сохранённые значения на воркере.',
    es: 'Opcionalmente inyecta un shell vanilla HTML/CSS/JS generado en el prompt de Developer (y Hardening) para que los productos reflejen motion, tokens y pulido de layout. Construye el pool offline: python scripts/generate_reference_templates.py --data-root ./data — salida en data/reference_templates/ y manifest.json. Presets en reference_templates/style_presets.json. Las variables AIFACTORY_REFERENCE_* anulan estos valores guardados en el worker.',
  },
  'settings.neuralUi.injectToggle': {
    en: 'Inject reference shell into Developer prompt',
    ru: 'Вставлять референс‑оболочку в промпт Developer',
    es: 'Inyectar shell de referencia en el prompt de Developer',
  },
  'settings.neuralUi.injectHelp': {
    en: 'Web deliverables only. Requires a generated pool (manifest + template folders on disk).',
    ru: 'Только веб‑артефакты. Нужен сгенерированный pool (manifest + папки шаблонов на диске).',
    es: 'Solo entregables web. Requiere pool generado (manifest + carpetas en disco).',
  },
  'settings.neuralUi.templatesDir': {
    en: 'Templates directory (optional)',
    ru: 'Каталог шаблонов (необязательно)',
    es: 'Directorio de plantillas (opcional)',
  },
  'settings.neuralUi.templatesDirPlaceholder': {
    en: 'Empty → <data_root>/reference_templates',
    ru: 'Пусто → <data_root>/reference_templates',
    es: 'Vacío → <data_root>/reference_templates',
  },
  'settings.neuralUi.selectionMode': {
    en: 'Selection mode',
    ru: 'Режим выбора',
    es: 'Modo de selección',
  },
  'settings.neuralUi.mode.random': {
    en: 'random (stable per product id)',
    ru: 'random (стабильно на product id)',
    es: 'random (estable por product id)',
  },
  'settings.neuralUi.mode.roundRobin': { en: 'round_robin', ru: 'round_robin', es: 'round_robin' },
  'settings.neuralUi.mode.fixed': { en: 'fixed', ru: 'fixed', es: 'fixed' },
  'settings.neuralUi.mode.matchSpec': {
    en: 'match_spec (keyword overlap with spec)',
    ru: 'match_spec (пересечение ключевых слов со спекой)',
    es: 'match_spec (solapamiento de palabras con la spec)',
  },
  'settings.neuralUi.templatesDetected': {
    en: 'Templates detected on disk:',
    ru: 'Шаблонов на диске:',
    es: 'Plantillas detectadas en disco:',
  },
  'settings.neuralUi.emptyPoolHint': {
    en: '— generate the pool (see command above), upload below, or check the templates directory path.',
    ru: '— сгенерируйте pool (см. команду выше), загрузите ниже или проверьте путь к каталогу.',
    es: '— genera el pool (ver comando arriba), sube abajo o revisa la ruta del directorio.',
  },
  'settings.neuralUi.installedTitle': {
    en: 'Installed templates',
    ru: 'Установленные шаблоны',
    es: 'Plantillas instaladas',
  },
  'settings.neuralUi.remove': {
    en: 'Remove',
    ru: 'Удалить',
    es: 'Quitar',
  },
  'settings.neuralUi.addCustomTitle': {
    en: 'Add custom template',
    ru: 'Добавить свой шаблон',
    es: 'Añadir plantilla personalizada',
  },
  'settings.neuralUi.addCustomBody': {
    en: 'Saves under your reference templates directory as a new folder with index.html (required) and optional style.css / app.js. Slug: lowercase letters, digits, hyphen, underscore.',
    ru: 'Сохраняется в каталоге референс‑шаблонов как новая папка с index.html (обязательно) и при необходимости style.css / app.js. Slug: строчные буквы, цифры, дефис, подчёркивание.',
    es: 'Se guarda en el directorio de plantillas como carpeta nueva con index.html (obligatorio) y opcional style.css / app.js. Slug: minúsculas, dígitos, guión, guión bajo.',
  },
  'settings.neuralUi.slugLabel': {
    en: 'Folder id (slug)',
    ru: 'ID папки (slug)',
    es: 'ID de carpeta (slug)',
  },
  'settings.neuralUi.slugPlaceholder': {
    en: 'my-brand-shell',
    ru: 'my-brand-shell',
    es: 'my-brand-shell',
  },
  'settings.neuralUi.displayTitle': {
    en: 'Display title (optional)',
    ru: 'Отображаемое название (необязательно)',
    es: 'Título visible (opcional)',
  },
  'settings.neuralUi.displayPlaceholder': {
    en: 'My brand shell',
    ru: 'My brand shell',
    es: 'My brand shell',
  },
  'settings.neuralUi.indexHtml': {
    en: 'index.html *',
    ru: 'index.html *',
    es: 'index.html *',
  },
  'settings.neuralUi.indexPlaceholder': {
    en: '<!DOCTYPE html>...',
    ru: '<!DOCTYPE html>...',
    es: '<!DOCTYPE html>...',
  },
  'settings.neuralUi.styleCss': {
    en: 'style.css (optional)',
    ru: 'style.css (необязательно)',
    es: 'style.css (opcional)',
  },
  'settings.neuralUi.appJs': {
    en: 'app.js (optional)',
    ru: 'app.js (необязательно)',
    es: 'app.js (opcional)',
  },
  'settings.neuralUi.saveTemplate': {
    en: 'Save template',
    ru: 'Сохранить шаблон',
    es: 'Guardar plantilla',
  },
  'settings.neuralUi.hint.random': {
    en: 'Same product always gets the same reference (hash of product id over the pool).',
    ru: 'Один и тот же продукт всегда получает тот же референс (хеш product id по пулу).',
    es: 'El mismo producto siempre recibe la misma referencia (hash del id sobre el pool).',
  },
  'settings.neuralUi.hint.roundRobin': {
    en: 'Each new Developer run advances to the next template in order (state file on disk).',
    ru: 'Каждый новый запуск Developer переходит к следующему шаблону по порядку (файл состояния на диске).',
    es: 'Cada nueva ejecución de Developer avanza al siguiente template en orden (estado en disco).',
  },
  'settings.neuralUi.hint.matchSpec': {
    en: 'Chooses the preset whose keywords best overlap with the specification and admin brief; falls back to random if there is no overlap.',
    ru: 'Выбирает пресет с лучшим пересечением ключевых слов со спекой и админским брифом; при отсутствии пересечения — random.',
    es: 'Elige el preset cuyas palabras mejor solapan con la spec y el brief; si no hay solape, vuelve a random.',
  },
  'settings.neuralUi.templateLabel': {
    en: 'Template',
    ru: 'Шаблон',
    es: 'Plantilla',
  },
  'settings.neuralUi.selectTemplate': {
    en: '— Select template —',
    ru: '— Выберите шаблон —',
    es: '— Seleccionar plantilla —',
  },
  'settings.neuralUi.unknownTemplateWarning': {
    en: 'Current id “{id}” is not in the catalog — pick above or fix the path.',
    ru: 'Текущий id «{id}» нет в каталоге — выберите выше или исправьте путь.',
    es: 'El id «{id}» no está en el catálogo — elige arriba o corrige la ruta.',
  },
  'settings.neuralUi.fixedIdLabel': {
    en: 'Fixed template id (folder name)',
    ru: 'Фиксированный id шаблона (имя папки)',
    es: 'Id fijo de plantilla (carpeta)',
  },
  'settings.neuralUi.fixedIdPlaceholder': {
    en: 'e.g. aurora-glass',
    ru: 'напр. aurora-glass',
    es: 'p. ej. aurora-glass',
  },
  'settings.neuralUi.maxPromptChars': {
    en: 'Max prompt chars:',
    ru: 'Макс. символов в промпте:',
    es: 'Máx. caracteres en el prompt:',
  },
  'settings.section.publicSite': {
    en: 'Public site URL',
    ru: 'URL публичной витрины',
    es: 'URL del sitio público',
  },
  'settings.publicSite.intro': {
    en: 'Canonical HTTPS origin for “Made with AI-Factory” watermarks on free-tier builds, referral share links, and embed badges. Overrides legacy aifactory.dev when the pipeline runs.',
    ru: 'Канонический HTTPS-адрес для водяного знака «Made with AI-Factory» (free), реферальных ссылок и embed-бейджа. Заменяет старый aifactory.dev при следующей сборке.',
    es: 'Origen HTTPS canónico para la marca “Made with AI-Factory” (plan free), enlaces de referidos y la insignia embed. Sustituye aifactory.dev en la próxima build.',
  },
  'settings.publicSite.urlLabel': {
    en: 'Public storefront URL (HTTPS)',
    ru: 'URL витрины (HTTPS)',
    es: 'URL de la tienda (HTTPS)',
  },
  'settings.publicSite.urlPlaceholder': {
    en: 'https://magic-ai-factory.com',
    ru: 'https://magic-ai-factory.com',
    es: 'https://magic-ai-factory.com',
  },
  'settings.section.siteBadge': {
    en: '“Built with AI-Factory” badge',
    ru: 'Бейдж «Built with AI-Factory»',
    es: 'Insignia “Built with AI-Factory”',
  },
  'settings.badge.intro': {
    en: 'After each developer build, inject a small fixed-corner link on every generated *.html file. Point it at your public repo (e.g. GitHub) so visitors can star or fork the factory.',
    ru: 'После каждой сборки Developer вставляйте маленькую ссылку в угол каждого *.html. Укажите на публичный репозиторий (например GitHub), чтобы гости могли поставить звезду или форкнуть фабрику.',
    es: 'Tras cada build de Developer, inyecta un enlace pequeño en la esquina de cada *.html. Apunta a tu repo público (p. ej. GitHub) para que los visitantes puedan dar estrella o hacer fork.',
  },
  'settings.badge.enable': {
    en: 'Enable badge on generated sites',
    ru: 'Включить бейдж на сгенерированных сайтах',
    es: 'Activar insignia en sitios generados',
  },
  'settings.badge.enableHelp': {
    en: 'Runs when Developer completes (needs HTTPS URL below).',
    ru: 'Срабатывает по завершении Developer (нужен HTTPS URL ниже).',
    es: 'Se aplica al terminar Developer (requiere URL HTTPS abajo).',
  },
  'settings.badge.urlLabel': {
    en: 'Badge link URL (HTTPS)',
    ru: 'URL ссылки бейджа (HTTPS)',
    es: 'URL del enlace de la insignia (HTTPS)',
  },
  'settings.badge.urlPlaceholder': {
    en: 'Leave empty to use Public site URL above',
    ru: 'Пусто — использовать URL витрины выше',
    es: 'Vacío — usar la URL pública de arriba',
  },
  'settings.section.headSnippet': {
    en: 'Head snippet on generated sites',
    ru: 'Сниппет в <head> сгенерированных сайтов',
    es: 'Snippet en <head> de sitios generados',
  },
  'settings.headSnippet.intro': {
    en: 'Raw HTML inserted before </head> on every *.html when Developer finishes (Google Analytics gtag, Yandex Metrica, meta verification tags, etc.). Leave empty to disable. Trusted admin content only. If the snippet includes a GA4 measurement id (G-…), the same id is loaded on this Next.js storefront (Explore, product pages) after save — no separate env needed.',
    ru: 'Сырой HTML вставляется перед </head> в каждом *.html по завершении Developer (gtag GA, Метрика, meta‑теги и т.д.). Пусто — отключено. Только доверенный контент админа. Если в сниппете есть GA4 id (G-…), тот же id подключается на витрине Next.js (Explore, страницы продуктов) после сохранения — отдельный env не нужен.',
    es: 'HTML crudo antes de </head> en cada *.html al terminar Developer (gtag de GA, Metrica, meta, etc.). Vacío para desactivar. Solo contenido de admin de confianza. Si el snippet incluye un id GA4 (G-…), el mismo id se carga en la tienda Next.js (Explore, productos) tras guardar — sin env aparte.',
  },
  'settings.headSnippet.label': {
    en: 'HTML / scripts for <head>',
    ru: 'HTML / скрипты для <head>',
    es: 'HTML / scripts para <head>',
  },
  'settings.headSnippet.placeholder': {
    en: '<!-- Google tag (gtag.js) -->\n<script async src="https://www.googletagmanager.com/gtag/js?id=G-67NJ81W2YY"></script>\n<script>\n  window.dataLayer = window.dataLayer || [];\n  function gtag(){dataLayer.push(arguments);}\n  gtag(\'js\', new Date());\n  gtag(\'config\', \'G-67NJ81W2YY\');\n</script>',
    ru: '<!-- Google tag (gtag.js) -->\n<script async src="https://www.googletagmanager.com/gtag/js?id=G-67NJ81W2YY"></script>\n<script>\n  window.dataLayer = window.dataLayer || [];\n  function gtag(){dataLayer.push(arguments);}\n  gtag(\'js\', new Date());\n  gtag(\'config\', \'G-67NJ81W2YY\');\n</script>',
    es: '<!-- Google tag (gtag.js) -->\n<script async src="https://www.googletagmanager.com/gtag/js?id=G-67NJ81W2YY"></script>\n<script>\n  window.dataLayer = window.dataLayer || [];\n  function gtag(){dataLayer.push(arguments);}\n  gtag(\'js\', new Date());\n  gtag(\'config\', \'G-67NJ81W2YY\');\n</script>',
  },
  'settings.demo.readonlyBanner': {
    en: 'Public demo mode: most Settings are read-only (backup, password, GA snippet, etc.). Exception: Factory hold at the top — pause or resume the pipeline on the shared demo host.',
    ru: 'Публичное демо: большинство «Настроек» только для чтения (бэкап, пароль, сниппет GA и т.д.). Исключение: «Пауза фабрики» вверху — можно остановить или запустить пайплайн на общем демо-хосте.',
    es: 'Demo público: la mayoría de Ajustes son solo lectura (copia, contraseña, snippet GA, etc.). Excepción: Pausa de la fábrica arriba — pausar o reanudar el pipeline en el host demo compartido.',
  },
  'settings.demo.settingsSaveBlocked': {
    en: 'Demo mode: settings are not saved. Set NEXT_PUBLIC_GA_MEASUREMENT_ID in .env or self-host without demo readonly.',
    ru: 'Демо-режим: настройки не сохраняются. Для GA укажите NEXT_PUBLIC_GA_MEASUREMENT_ID в .env или поднимите свой инстанс без demo readonly.',
    es: 'Modo demo: los ajustes no se guardan. Use NEXT_PUBLIC_GA_MEASUREMENT_ID en .env o autoaloje sin demo readonly.',
  },
  'settings.demo.headSnippetBlocked': {
    en: 'This field cannot be saved on the shared demo. Use NEXT_PUBLIC_GA_MEASUREMENT_ID=G-67NJ81W2YY in .env (already recommended for magic-ai-factory.com) or self-host to edit and save the snippet here.',
    ru: 'На общем демо поле не сохраняется. Для счётчика GA используйте NEXT_PUBLIC_GA_MEASUREMENT_ID=G-67NJ81W2YY в .env (рекомендуется для magic-ai-factory.com) или свой инстанс без demo readonly.',
    es: 'En el demo compartido no se guarda. Para GA use NEXT_PUBLIC_GA_MEASUREMENT_ID=G-67NJ81W2YY en .env o autoaloje sin demo readonly.',
  },
  'settings.headSnippet.footer': {
    en: 'Max 100,000 characters (server truncates beyond that). Already-built pages are not rewritten; run Developer again or edit HTML on disk to apply changes retroactively. This field autosaves a few seconds after edits — blur the field to save immediately.',
    ru: 'Макс. 100 000 символов (сервер обрежет). Уже собранные страницы не переписываются; перезапустите Developer или правьте HTML на диске для ретроактивных изменений. Поле автосохраняется через несколько секунд — уберите фокус для немедленного сохранения.',
    es: 'Máx. 100 000 caracteres (el servidor trunca). Las páginas ya construidas no se reescriben; ejecuta Developer o edita el HTML en disco para cambios retroactivos. Este campo se autoguarda tras unos segundos — pierde el foco para guardar al instante.',
  },
  'settings.headSnippet.charCount': {
    en: '{n} / 100,000',
    ru: '{n} / 100 000',
    es: '{n} / 100.000',
  },
  'settings.toast.refSlugRequired': {
    en: 'Enter a folder id (slug), e.g. my-brand-shell',
    ru: 'Введите id папки (slug), напр. my-brand-shell',
    es: 'Introduce un id de carpeta (slug), p. ej. my-brand-shell',
  },
  'settings.toast.refHtmlRequired': {
    en: 'index.html content is required',
    ru: 'Нужно содержимое index.html',
    es: 'Se requiere contenido de index.html',
  },
  'settings.toast.refTemplateSaved': {
    en: 'Template “{slug}” saved',
    ru: 'Шаблон «{slug}» сохранён',
    es: 'Plantilla “{slug}” guardada',
  },
  'settings.toast.uploadFailed': {
    en: 'Upload failed',
    ru: 'Загрузка не удалась',
    es: 'Error al subir',
  },
  'settings.confirm.deleteTemplate': {
    en: 'Remove reference template folder “{path}” from disk? This cannot be undone.',
    ru: 'Удалить папку референс‑шаблона «{path}» с диска? Это необратимо.',
    es: '¿Quitar la carpeta de plantilla «{path}» del disco? No se puede deshacer.',
  },
  'settings.toast.templateRemoved': {
    en: 'Template removed',
    ru: 'Шаблон удалён',
    es: 'Plantilla eliminada',
  },
  'settings.toast.deleteFailed': {
    en: 'Delete failed',
    ru: 'Не удалось удалить',
    es: 'Error al eliminar',
  },
};
