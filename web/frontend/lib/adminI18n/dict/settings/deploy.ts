import type { I18nDict } from '../../types';

export const DEPLOY_SETTINGS_DICT: I18nDict = {
  'settings.section.gitRemote': {
    en: 'Git Remote Configuration',
    ru: 'Настройка удалённого Git',
    es: 'Configuración remota de Git',
  },
  'settings.git.intro': {
    en: 'Configure the remote Git repository where product code will be pushed. Used by the Pipeline → Git workflow.',
    ru: 'Настройте удалённый Git‑репозиторий, куда будет пушиться код продуктов. Используется в Pipeline → Git.',
    es: 'Configura el repositorio Git remoto donde se subirá el código de los productos. Lo usa el flujo Pipeline → Git.',
  },
  'settings.git.remoteUrl': {
    en: 'Remote URL',
    ru: 'URL удалённого репозитория',
    es: 'URL remota',
  },
  'settings.git.remoteUrlPlaceholder': {
    en: 'https://github.com/your-org/repo.git',
    ru: 'https://github.com/your-org/repo.git',
    es: 'https://github.com/your-org/repo.git',
  },
  'settings.git.defaultBranch': {
    en: 'Default Branch',
    ru: 'Ветка по умолчанию',
    es: 'Rama predeterminada',
  },
  'settings.section.docker': {
    en: 'Docker Registry Credentials',
    ru: 'Учётные данные Docker Registry',
    es: 'Credenciales del registro Docker',
  },
  'settings.docker.intro': {
    en: 'Docker registry credentials for pushing built images (e.g., Docker Hub, GitHub Container Registry).',
    ru: 'Учётные данные реестра Docker для push собранных образов (например, Docker Hub, GitHub Container Registry).',
    es: 'Credenciales del registro Docker para publicar imágenes compiladas (p. ej. Docker Hub, GitHub Container Registry).',
  },
  'settings.docker.registryUrl': {
    en: 'Registry URL',
    ru: 'URL реестра',
    es: 'URL del registro',
  },
  'settings.docker.registryPlaceholder': {
    en: 'docker.io (default)',
    ru: 'docker.io (по умолчанию)',
    es: 'docker.io (predeterminado)',
  },
  'settings.docker.username': {
    en: 'Username',
    ru: 'Имя пользователя',
    es: 'Usuario',
  },
  'settings.docker.usernamePlaceholder': {
    en: 'Docker registry username',
    ru: 'Логин Docker registry',
    es: 'Usuario del registro Docker',
  },
  'settings.docker.password': {
    en: 'Password / Token',
    ru: 'Пароль / токен',
    es: 'Contraseña / token',
  },
  'settings.docker.passwordPlaceholder': {
    en: 'Docker registry password or access token',
    ru: 'Пароль реестра или токен доступа',
    es: 'Contraseña del registro o token de acceso',
  },
  'settings.section.autoPublish': {
    en: 'Auto-publish after DevOps',
    ru: 'Автопубликация после DevOps',
    es: 'Auto-publicación tras DevOps',
  },
  'settings.autoPublish.intro': {
    en: 'Deploy data/code/<product_id>/ to a static host when the DevOps stage succeeds. Install the matching CLI on the factory host and set tokens via environment variables (VERCEL_TOKEN, NETLIFY_AUTH_TOKEN, CLOUDFLARE_API_TOKEN). See docs/auto-publish.md.',
    ru: 'Публикуйте data/code/<product_id>/ на статический хост при успешном DevOps. Установите нужный CLI на хост фабрики и задайте токены через переменные окружения (VERCEL_TOKEN, NETLIFY_AUTH_TOKEN, CLOUDFLARE_API_TOKEN). См. docs/auto-publish.md.',
    es: 'Publica data/code/<product_id>/ en un host estático cuando DevOps tenga éxito. Instala el CLI adecuado en el host y define tokens con variables de entorno (VERCEL_TOKEN, NETLIFY_AUTH_TOKEN, CLOUDFLARE_API_TOKEN). Ver docs/auto-publish.md.',
  },
  'settings.autoPublish.enable': {
    en: 'Enable auto-publish',
    ru: 'Включить автопубликацию',
    es: 'Activar auto-publicación',
  },
  'settings.autoPublish.enableHelp': {
    en: 'Runs after DevOps completes (non-blocking).',
    ru: 'Запускается после завершения DevOps (не блокирует).',
    es: 'Se ejecuta al terminar DevOps (sin bloquear).',
  },
  'settings.autoPublish.provider': {
    en: 'Provider',
    ru: 'Провайдер',
    es: 'Proveedor',
  },
  'settings.autoPublish.provider.none': { en: 'none', ru: 'нет', es: 'ninguno' },
  'settings.autoPublish.provider.vercel': { en: 'vercel', ru: 'vercel', es: 'vercel' },
  'settings.autoPublish.provider.netlify': { en: 'netlify', ru: 'netlify', es: 'netlify' },
  'settings.autoPublish.provider.cloudflare': { en: 'cloudflare_pages', ru: 'cloudflare_pages', es: 'cloudflare_pages' },
  'settings.autoPublish.netlifySiteId': {
    en: 'Netlify site ID (optional)',
    ru: 'ID сайта Netlify (необязательно)',
    es: 'ID del sitio Netlify (opcional)',
  },
  'settings.autoPublish.netlifyPlaceholder': {
    en: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    ru: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    es: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
  },
  'settings.autoPublish.cfProject': {
    en: 'Cloudflare Pages project name (optional)',
    ru: 'Имя проекта Cloudflare Pages (необязательно)',
    es: 'Nombre del proyecto Cloudflare Pages (opcional)',
  },
  'settings.autoPublish.cfPlaceholder': {
    en: 'aifactory-my-product',
    ru: 'aifactory-my-product',
    es: 'aifactory-my-product',
  },
  'settings.section.railway': {
    en: 'Railway (full_software)',
    ru: 'Railway (full_software)',
    es: 'Railway (full_software)',
  },
  'settings.railway.intro': {
    en: 'After DevOps, when the product specification is full_software, the factory records deploy metadata under data/state/<product_id>/railway_deploy.json so you can trigger a separate CI step (GitHub Action calling Railway’s API, or Git-connected deploy). Set RAILWAY_TOKEN on the factory host — never in YAML. See docs/deploy-full-software-cloud.md.',
    ru: 'После DevOps, если спецификация full_software, фабрика записывает метаданные деплоя в data/state/<product_id>/railway_deploy.json для отдельного шага CI (GitHub Action с API Railway или деплой через Git). Задайте RAILWAY_TOKEN на хосте фабрики — не в YAML. См. docs/deploy-full-software-cloud.md.',
    es: 'Tras DevOps, si la especificación es full_software, la fábrica guarda metadatos en data/state/<product_id>/railway_deploy.json para un paso CI aparte (GitHub Action con la API de Railway o deploy conectado a Git). Define RAILWAY_TOKEN en el host — nunca en YAML. Ver docs/deploy-full-software-cloud.md.',
  },
  'settings.railway.tokenWarning': {
    en: 'RAILWAY_TOKEN is not set in the environment — enable the toggle below after adding the token to .env / container secrets.',
    ru: 'RAILWAY_TOKEN не задан в окружении — включите переключатель ниже после добавления токена в .env или секреты контейнера.',
    es: 'RAILWAY_TOKEN no está en el entorno — activa el interruptor tras añadir el token a .env o secretos del contenedor.',
  },
  'settings.railway.recordIntent': {
    en: 'Record Railway deploy intent after DevOps',
    ru: 'Записывать намерение деплоя Railway после DevOps',
    es: 'Registrar intención de deploy Railway tras DevOps',
  },
  'settings.railway.recordIntentHelp': {
    en: 'Only for full_software specs; requires RAILWAY_TOKEN.',
    ru: 'Только для спецификаций full_software; нужен RAILWAY_TOKEN.',
    es: 'Solo para specs full_software; requiere RAILWAY_TOKEN.',
  },
  'settings.railway.projectId': {
    en: 'Railway project ID',
    ru: 'ID проекта Railway',
    es: 'ID del proyecto Railway',
  },
  'settings.railway.projectIdPlaceholder': {
    en: 'UUID from Railway dashboard',
    ru: 'UUID из панели Railway',
    es: 'UUID del panel de Railway',
  },
  'settings.railway.envName': {
    en: 'Environment name (optional)',
    ru: 'Имя окружения (необязательно)',
    es: 'Nombre del entorno (opcional)',
  },
  'settings.railway.envNamePlaceholder': {
    en: 'production',
    ru: 'production',
    es: 'production',
  },
  'settings.railway.envId': {
    en: 'Environment ID (optional, UUID for Railway API)',
    ru: 'ID окружения (необязательно, UUID для API Railway)',
    es: 'ID del entorno (opcional, UUID para la API de Railway)',
  },
  'settings.railway.envIdPlaceholder': {
    en: 'From Railway dashboard / GraphQL — for redeploy scripts',
    ru: 'Из дашборда Railway / GraphQL — для скриптов передеплоя',
    es: 'Del panel / GraphQL — para scripts de redeploy',
  },
  'settings.railway.serviceId': {
    en: 'Service ID (optional)',
    ru: 'ID сервиса (необязательно)',
    es: 'ID del servicio (opcional)',
  },
  'settings.railway.serviceIdPlaceholder': {
    en: 'For dashboards / future API wiring',
    ru: 'Для дашбордов / будущей интеграции API',
    es: 'Para paneles / futura API',
  },
};
