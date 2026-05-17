export type AdminLocale = 'en' | 'ru' | 'es';

type Dict = Record<string, Record<AdminLocale, string>>;

const DICT: Dict = {
  'app.adminPanel': { en: 'Admin Panel', ru: 'Админ-панель', es: 'Panel de administración' },
  /** Logo link → marketing home */
  'app.backToSite': {
    en: 'Back to site',
    ru: 'На главную (маркет)',
    es: 'Volver al sitio',
  },
  'app.logout': { en: 'Logout', ru: 'Выйти', es: 'Cerrar sesión' },
  'app.language': { en: 'Language', ru: 'Язык', es: 'Idioma' },
  'sidebar.expandMenu': { en: 'Expand menu', ru: 'Развернуть меню', es: 'Expandir menú' },
  'sidebar.collapseMenu': { en: 'Collapse menu', ru: 'Свернуть меню', es: 'Contraer menú' },
  'newProduct.contentLanguage': {
    en: 'Landing & UI copy language',
    ru: 'Язык лендинга и UI-копирайта',
    es: 'Idioma del landing y textos UI',
  },
  'newProduct.contentLanguageHint': {
    en: 'Auto: match a clear brief (RU→RU, EN→EN); mixed/unclear brief → English; silent brief → current admin UI language. Override to force a locale.',
    ru: 'Авто: явный язык брифа (RU→RU, EN→EN); смешанный/неясный бриф → английский; пустой бриф → язык интерфейса админки. Выбор языка — принудительная локаль.',
    es: 'Auto: idioma claro del brief (RU→RU, EN→EN); brief mixto/ambiguo → inglés; brief vacío → idioma UI del admin. Elegir idioma fuerza la locale.',
  },
  'tab.dashboard': { en: 'Dashboard', ru: 'Дашборд', es: 'Panel' },
  'tab.setup': { en: 'Setup', ru: 'Настройка', es: 'Configuración' },
  'tab.monitor': { en: 'Live Monitor', ru: 'Мониторинг', es: 'Monitor en vivo' },
  'tab.pipeline': { en: 'Pipeline', ru: 'Пайплайн', es: 'Pipeline' },
  'tab.newProduct': { en: 'New Product', ru: 'Новый продукт', es: 'Nuevo producto' },
  'tab.workshop': { en: 'Workshop', ru: 'Мастерская', es: 'Taller' },
  'tab.files': { en: 'Files', ru: 'Файлы', es: 'Archivos' },
  'tab.agents': { en: 'Agents', ru: 'Агенты', es: 'Agentes' },
  'tab.providers': { en: 'LLM Providers', ru: 'Провайдеры LLM', es: 'Proveedores LLM' },
  'tab.llmLogs': { en: 'LLM Logs', ru: 'Логи LLM', es: 'Registros LLM' },
  'tab.agentLogs': { en: 'Agent Logs', ru: 'Логи агентов', es: 'Registros de agentes' },
  'tab.security': { en: 'Security', ru: 'Безопасность', es: 'Seguridad' },
  'tab.sandbox': { en: 'Sandbox', ru: 'Песочница', es: 'Sandbox' },
  'tab.director': { en: 'Director AI', ru: 'Director AI', es: 'Director AI' },
  /** Ranked intake from discovery signals — not support tickets. */
  'tab.discovery': {
    en: 'Signals → Ideas',
    ru: 'Сигналы → идеи',
    es: 'Señales → ideas',
  },
  'discovery.pageTitle': {
    en: 'Ranked ideas from signals',
    ru: 'Рейтинг идей по сигналам',
    es: 'Ideas clasificadas desde señales',
  },
  'discovery.ideasLabel': { en: 'ideas', ru: 'идей', es: 'ideas' },
  'discovery.signalsLabel': { en: 'signals', ru: 'сигналов', es: 'señales' },
  'discovery.refresh': { en: 'Refresh', ru: 'Обновить', es: 'Actualizar' },
  'discovery.queueTop': {
    en: 'Send top idea to pipeline',
    ru: 'Отправить топ-идею в пайплайн',
    es: 'Enviar idea top al pipeline',
  },
  'discovery.refreshing': { en: 'Refreshing…', ru: 'Обновление…', es: 'Actualizando…' },
  'discovery.queueing': { en: 'Queueing…', ru: 'В очередь…', es: 'Encolando…' },
  'discovery.empty': {
    en: 'No ranked ideas yet. Run refresh.',
    ru: 'Пока нет идей в рейтинге. Нажмите «Обновить».',
    es: 'Sin ideas aún. Pulse actualizar.',
  },
  'discovery.ideaQueueSection': {
    en: 'Ranked idea queue',
    ru: 'Очередь отранжированных идей',
    es: 'Cola de ideas rankeadas',
  },
  'discovery.directorRefresh': {
    en: 'Refresh ranked ideas',
    ru: 'Обновить рейтинг идей',
    es: 'Actualizar ranking de ideas',
  },
  'discovery.directorQueueTop': {
    en: 'Queue top idea to pipeline',
    ru: 'Топ-идея в пайплайн',
    es: 'Top idea al pipeline',
  },
  'discovery.noRankedYet': {
    en: 'No ranked ideas yet. Run refresh to generate the queue.',
    ru: 'Рейтинга пока нет. Обновите — сгенерируется очередь.',
    es: 'Sin ranking aún. Actualice para generar la cola.',
  },
  'discovery.pruning': {
    en: 'Signal pruning removed {n} stale rows (TTL / max-size policy).',
    ru: 'Очистка сигналов: удалено {n} устаревших записей (TTL / лимит размера).',
    es: 'Poda de señales: eliminadas {n} filas obsoletas (TTL / tamaño máximo).',
  },
  'discovery.toastRefreshed': {
    en: 'Ranked ideas refreshed',
    ru: 'Рейтинг идей обновлён',
    es: 'Ideas clasificadas actualizadas',
  },
  'discovery.toastQueuedWithId': {
    en: 'Pipeline product queued: {id}',
    ru: 'В пайплайн добавлен продукт {id}',
    es: 'Producto encolado: {id}',
  },
  'tab.settings': { en: 'Settings', ru: 'Настройки', es: 'Configuración' },
  'tab.chat': { en: 'Corporate Chat', ru: 'Корпоративный чат', es: 'Chat corporativo' },
  'tab.brainstorming': { en: 'Brainstorming', ru: 'Брейншторм', es: 'Lluvia de ideas' },
  'tab.supportQueue': { en: 'Support escalations', ru: 'Эскалации поддержки', es: 'Escalaciones de soporte' },
  'tab.outreach': { en: 'Outreach', ru: 'Аутрич', es: 'Difusión' },
  'tab.users': {
    en: 'Users & access',
    ru: 'Пользователи и доступ',
    es: 'Usuarios y acceso',
  },
  'users.title': { en: 'Admin users', ru: 'Пользователи админки', es: 'Usuarios administradores' },
  'users.subtitle': {
    en: 'Accounts that can sign in to this panel — roles limit what each user can change.',
    ru: 'Учётные записи для входа в панель — роли ограничивают доступ к разделам и действиям.',
    es: 'Cuentas que pueden iniciar sesión — los roles limitan lo que cada usuario puede hacer.',
  },
  'users.refresh': { en: 'Refresh', ru: 'Обновить', es: 'Actualizar' },
  'users.add': { en: 'Add user', ru: 'Добавить', es: 'Añadir' },
  'users.loading': { en: 'Loading…', ru: 'Загрузка…', es: 'Cargando…' },
  'users.colUser': { en: 'User', ru: 'Пользователь', es: 'Usuario' },
  'users.colRole': { en: 'Role', ru: 'Роль', es: 'Rol' },
  'users.colStatus': { en: 'Status', ru: 'Статус', es: 'Estado' },
  'users.colActions': { en: 'Actions', ru: 'Действия', es: 'Acciones' },
  'users.active': { en: 'Active', ru: 'Активен', es: 'Activo' },
  'users.disabled': { en: 'Disabled', ru: 'Отключён', es: 'Inactivo' },
  'users.modalTitle': { en: 'New admin user', ru: 'Новый пользователь', es: 'Nuevo usuario' },
  'users.username': { en: 'Username', ru: 'Имя пользователя', es: 'Nombre de usuario' },
  'users.password': { en: 'Password (min 12 chars)', ru: 'Пароль (мин. 12 символов)', es: 'Contraseña (mín. 12)' },
  'users.role': { en: 'Role', ru: 'Роль', es: 'Rol' },
  'users.role.viewer': { en: 'Viewer', ru: 'Наблюдатель', es: 'Observador' },
  'users.role.operator': { en: 'Operator', ru: 'Оператор', es: 'Operador' },
  'users.role.admin': { en: 'Admin', ru: 'Администратор', es: 'Administrador' },
  'users.role.super_admin': { en: 'Super admin', ru: 'Супер-админ', es: 'Superadmin' },
  'users.roleDesc.viewer': {
    en: 'Read-only dashboards and status; cannot change data or open secrets/settings.',
    ru: 'Только просмотр дашбордов и статуса; нельзя менять данные и открывать секреты/настройки.',
    es: 'Solo lectura de paneles y estado; no puede modificar datos ni ver secretos/ajustes.',
  },
  'users.roleDesc.operator': {
    en: 'Runs pipeline and queue; cannot edit providers, platform settings, or users.',
    ru: 'Запускает пайплайн и очередь; нельзя менять провайдеров, настройки платформы и пользователей.',
    es: 'Ejecuta pipeline y cola; no puede editar proveedores, ajustes de plataforma ni usuarios.',
  },
  'users.roleDesc.admin': {
    en: 'Full configuration except managing admin accounts.',
    ru: 'Полная настройка, кроме управления учётными записями админки.',
    es: 'Configuración completa salvo gestionar cuentas del panel.',
  },
  'users.roleDesc.super_admin': {
    en: 'Full access including Users & access (create/remove accounts).',
    ru: 'Полный доступ, включая «Пользователи и доступ» (создание/удаление учётных записей).',
    es: 'Acceso total, incluido usuarios del panel (crear/eliminar cuentas).',
  },
  'users.cancel': { en: 'Cancel', ru: 'Отмена', es: 'Cancelar' },
  'users.save': { en: 'Create', ru: 'Создать', es: 'Crear' },
  'users.created': { en: 'User created', ru: 'Пользователь создан', es: 'Usuario creado' },
  'users.deleted': { en: 'User removed', ru: 'Пользователь удалён', es: 'Usuario eliminado' },
  'users.passwordMin': {
    en: 'Password must be at least 12 characters',
    ru: 'Пароль не короче 12 символов',
    es: 'La contraseña debe tener al menos 12 caracteres',
  },
  'users.confirmDelete': {
    en: 'Remove user {name}? They will no longer be able to sign in.',
    ru: 'Удалить пользователя {name}? Вход будет невозможен.',
    es: '¿Eliminar a {name}? Ya no podrá iniciar sesión.',
  },
  'security.demoPassword.title': {
    en: 'Change the sandbox demo password',
    ru: 'Смените демо-пароль песочницы',
    es: 'Cambie la contraseña demo del sandbox',
  },
  'security.demoPassword.body': {
    en: 'The factory is still using the default AIFACTORY_SANDBOX_DEMO_PASSWORD. Anyone who can reach generated compose previews could sign in with the known demo credentials. Set a strong secret in your host environment (and .env), rebuild or restart the app, then rotate credentials in any already-running sandbox stacks.',
    ru: 'Фабрика всё ещё использует значение AIFACTORY_SANDBOX_DEMO_PASSWORD по умолчанию. У кого есть доступ к поднятым compose-превью, тот может войти под известными демо-учётными данными. Задайте надёжный секрет в окружении хоста (и в .env), пересоберите или перезапустите приложение, затем смените учётные данные в уже запущенных песочницах при необходимости.',
    es: 'La fábrica sigue usando AIFACTORY_SANDBOX_DEMO_PASSWORD por defecto. Quien acceda a las vistas previas compose podría iniciar sesión con credenciales demo conocidas. Defina un secreto fuerte en el entorno del host (.env), reconstruya o reinicie la app y rote credenciales en sandboxes ya en ejecución.',
  },
  'security.demoPassword.dismiss': {
    en: 'Hide until next session',
    ru: 'Скрыть до следующего сеанса',
    es: 'Ocultar hasta la próxima sesión',
  },
  'security.demoPassword.openSandbox': {
    en: 'Sandbox tab',
    ru: 'Вкладка «Песочница»',
    es: 'Pestaña Sandbox',
  },
};

export function detectAdminLocale(): AdminLocale {
  if (typeof window === 'undefined') return 'en';
  const raw = window.localStorage.getItem('admin_locale');
  if (raw === 'ru' || raw === 'es') return raw;
  return 'en';
}

export function saveAdminLocale(locale: AdminLocale): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem('admin_locale', locale);
}

export function t(locale: AdminLocale, key: string): string {
  const row = DICT[key];
  if (!row) return key;
  return row[locale] ?? row.en ?? key;
}

/** Replace `{name}` placeholders in a translated string. */
export function tVars(locale: AdminLocale, key: string, vars: Record<string, string | number>): string {
  let s = t(locale, key);
  for (const [k, v] of Object.entries(vars)) {
    s = s.split(`{${k}}`).join(String(v));
  }
  return s;
}
