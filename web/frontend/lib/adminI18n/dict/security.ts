import type { I18nDict } from '../types';

export const SECURITY_DICT: I18nDict = {
  'security.tabTitle': {
    en: 'Security',
    ru: 'Безопасность',
    es: 'Seguridad',
    fr: 'Sécurité',
    zh: '安全',
  },
  'security.section.reportsTitle': {
    en: 'Security Reports',
    ru: 'Отчёты безопасности',
    es: 'Informes de seguridad',
    fr: 'Rapports de sécurité',
    zh: '安全报告',
  },
  'security.loading.catalog': {
    en: 'Loading pipeline catalog…',
    ru: 'Загрузка каталога пайплайна…',
    es: 'Cargando catálogo del pipeline…',
    fr: 'Chargement du catalogue du pipeline…',
    zh: '正在加载流水线目录…',
  },
  'security.catalogErrorBody': {
    en: 'Check network, admin session, and backend logs. Refresh the page to try again.',
    ru: 'Проверьте сеть, сессию администратора и логи бэкенда. Обновите страницу и повторите попытку.',
    es: 'Comprueba la red, la sesión de admin y los logs del backend. Recarga la página para reintentar.',
    fr: 'Vérifiez le réseau, la session admin et les logs du backend. Actualisez la page pour réessayer.',
    zh: '请检查网络、管理员会话和后端日志。刷新页面重试。',
  },
  'security.catalogEmptyExplainer': {
    en:
      'With SQLite enabled, the list comes from the database. Security agent reports appear here only for products that have completed the Security stage (after QA). If the pipeline is empty or nothing has reached Security yet, this list stays empty.',
    ru:
      'При SQLite список берётся из БД. Отчёты агента безопасности здесь только у продуктов, которые прошли этап Security (после QA). Если пайплайн пуст или никто до Security не дошёл — список останется пустым.',
    es:
      'Con SQLite habilitado, la lista viene de la base de datos. Los informes del agente de seguridad aparecen aquí solo para productos que completaron la etapa Security (tras QA). Si el pipeline está vacío o nada llegó a Security, la lista queda vacía.',
    fr:
      'Avec SQLite activé, la liste provient de la base de données. Les rapports de l\'agent de sécurité n\'apparaissent ici que pour les produits ayant terminé l\'étape Security (après QA). Si le pipeline est vide ou que rien n\'a encore atteint Security, cette liste reste vide.',
    zh:
      '启用 SQLite 后，列表来自数据库。安全代理报告仅针对已完成 Security 阶段（QA 之后）的产品显示。如果流水线为空或尚无产品到达 Security，此列表将保持为空。',
  },
  'security.section.auditLogsTitle': {
    en: 'Security Audit Logs',
    ru: 'Журнал аудита безопасности',
    es: 'Logs de auditoría de seguridad',
    fr: 'Journaux d\'audit de sécurité',
    zh: '安全审计日志',
  },
  'security.loading.audit': {
    en: 'Loading audit logs…',
    ru: 'Загрузка журнала аудита…',
    es: 'Cargando registros de auditoría…',
    fr: 'Chargement des journaux d\'audit…',
    zh: '正在加载审计日志…',
  },
  'security.loading.report': {
    en: 'Loading security report…',
    ru: 'Загрузка отчёта безопасности…',
    es: 'Cargando informe de seguridad…',
    fr: 'Chargement du rapport de sécurité…',
    zh: '正在加载安全报告…',
  },
  'security.label.securityScore': {
    en: 'Security Score:',
    ru: 'Оценка безопасности:',
    es: 'Puntuación de seguridad:',
    fr: 'Score de sécurité :',
    zh: '安全评分：',
  },
};
