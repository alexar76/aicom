import type { I18nDict } from '../types';

export const LOGIN_DICT: I18nDict = {
  'login.title': { en: 'Admin Login', ru: 'Вход в админку', es: 'Inicio de sesión admin' },
  'login.subtitle': { en: 'AI-Factory v2.1 Management Panel', ru: 'Панель управления AI-Factory v2.1', es: 'Panel AI-Factory v2.1' },
  'login.username': { en: 'Username', ru: 'Имя пользователя', es: 'Usuario' },
  'login.password': { en: 'Password', ru: 'Пароль', es: 'Contraseña' },
  'login.usernamePlaceholder': { en: 'admin', ru: 'admin', es: 'admin' },
  'login.passwordPlaceholder': { en: 'Enter admin password', ru: 'Введите пароль администратора', es: 'Contraseña de administrador' },
  'login.submit': { en: 'Login', ru: 'Войти', es: 'Entrar' },
  'login.webauthn': { en: 'Sign in with passkey', ru: 'Войти с passkey', es: 'Entrar con passkey' },
  'login.verify2fa': { en: 'Verify 2FA', ru: 'Подтвердить 2FA', es: 'Verificar 2FA' },
  'login.totp': { en: '2FA Code', ru: 'Код 2FA', es: 'Código 2FA' },
  'login.totpPlaceholder': { en: 'Enter 6-digit code', ru: '6-значный код', es: 'Código de 6 dígitos' },
  'login.webauthnHint': {
    en: 'Use your passkey (Touch ID, Windows Hello, security key) on the next step.',
    ru: 'Используйте passkey (Touch ID, Windows Hello, ключ) на следующем шаге.',
    es: 'Use su passkey (Touch ID, Windows Hello, llave) en el siguiente paso.',
  },
  'login.footer': {
    en: 'Secure admin access with password and optional 2FA',
    ru: 'Защищённый вход с паролем и опциональной 2FA',
    es: 'Acceso seguro con contraseña y 2FA opcional',
  },
  'login.invalidCredentials': { en: 'Invalid credentials', ru: 'Неверные учётные данные', es: 'Credenciales inválidas' },
  'login.language': { en: 'Language', ru: 'Язык', es: 'Idioma' },
  'login.ssoDivider': { en: 'or', ru: 'или', es: 'o' },
  'login.sso': {
    en: 'Sign in with SSO',
    ru: 'Войти через SSO',
    es: 'Iniciar sesión con SSO',
  },
  'login.publicDemoSubtitle': {
    en: 'Shared public demo — explore the admin panel (read-only)',
    ru: 'Общее публичное демо — панель администратора (только просмотр)',
    es: 'Demo pública compartida — panel admin (solo lectura)',
  },
  'login.publicDemoSubmit': {
    en: 'Enter admin demo',
    ru: 'Открыть демо',
    es: 'Entrar al demo',
  },
  'login.publicDemoFooter': {
    en: 'No password on the shared demo host. Self-host for full owner controls.',
    ru: 'На общем демо-хосте пароль не нужен. Для полного контроля — свой инстанс.',
    es: 'Sin contraseña en el host demo compartido. Auto-aloje para control total.',
  },
};
