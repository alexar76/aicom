import type { I18nDict } from '../types';

export const SECURITY_DICT: I18nDict = {
  'security.tabTitle': {
    en: 'Security',
    ru: 'Безопасность',
    es: 'Seguridad',
  },
  'security.section.reportsTitle': {
    en: 'Security Reports',
    ru: 'Отчёты безопасности',
    es: 'Informes de seguridad',
  },
  'security.loading.catalog': {
    en: 'Loading pipeline catalog…',
    ru: 'Загрузка каталога пайплайна…',
    es: 'Cargando catálogo del pipeline…',
  },
  'security.catalogErrorBody': {
    en: 'Check network, admin session, and backend logs. Refresh the page to try again.',
    ru: 'Проверьте сеть, сессию администратора и логи бэкенда. Обновите страницу и повторите попытку.',
    es: 'Comprueba la red, la sesión de admin y los logs del backend. Recarga la página para reintentar.',
  },
  'security.catalogEmptyExplainer': {
    en:
      'With SQLite enabled, the list comes from the database. Security agent reports appear here only for products that have completed the Security stage (after QA). If the pipeline is empty or nothing has reached Security yet, this list stays empty.',
    ru:
      'При SQLite список берётся из БД. Отчёты агента безопасности здесь только у продуктов, которые прошли этап Security (после QA). Если пайплайн пуст или никто до Security не дошёл — список останется пустым.',
    es:
      'Con SQLite habilitado, la lista viene de la base de datos. Los informes del agente de seguridad aparecen aquí solo para productos que completaron la etapa Security (tras QA). Si el pipeline está vacío o nada llegó a Security, la lista queda vacía.',
  },
  'security.section.auditLogsTitle': {
    en: 'Security Audit Logs',
    ru: 'Журнал аудита безопасности',
    es: 'Logs de auditoría de seguridad',
  },
  'security.loading.audit': {
    en: 'Loading audit logs…',
    ru: 'Загрузка журнала аудита…',
    es: 'Cargando registros de auditoría…',
  },
  'security.loading.report': {
    en: 'Loading security report…',
    ru: 'Загрузка отчёта безопасности…',
    es: 'Cargando informe de seguridad…',
  },
  'security.label.securityScore': {
    en: 'Security Score:',
    ru: 'Оценка безопасности:',
    es: 'Puntuación de seguridad:',
  },
};
