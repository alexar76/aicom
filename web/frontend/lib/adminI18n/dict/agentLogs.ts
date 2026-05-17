import type { I18nDict } from '../types';

export const AGENT_LOGS_DICT: I18nDict = {
  'agentLogs.title': {
    en: 'Agent Execution Logs',
    ru: 'Журнал выполнения агентов',
    es: 'Logs de ejecución de agentes',
  },
  'agentLogs.searchPlaceholder': {
    en: 'Search message / agent / payload…',
    ru: 'Поиск по сообщению / агенту / данным…',
    es: 'Buscar mensaje / agente / payload…',
  },
  'agentLogs.errorsOnly': { en: 'Errors only', ru: 'Только ошибки', es: 'Solo errores' },
  'agentLogs.agentAll': { en: 'All Agents', ru: 'Все агенты', es: 'Todos los agentes' },
  'agentLogs.fromLocal': { en: 'From (local)', ru: 'С (локально)', es: 'Desde (local)' },
  'agentLogs.toLocal': { en: 'To (local)', ru: 'По (локально)', es: 'Hasta (local)' },
  'agentLogs.refresh': { en: 'Refresh', ru: 'Обновить', es: 'Actualizar' },
  'agentLogs.summary': {
    en: 'Showing {filtered} filtered / {loaded} loaded / {total} in time window',
    ru: 'Показано {filtered} после фильтра / {loaded} загружено / {total} в окне времени',
    es: 'Mostrando {filtered} filtradas / {loaded} cargadas / {total} en la ventana',
  },
  'agentLogs.loading': {
    en: 'Loading agent logs…',
    ru: 'Загрузка логов агентов…',
    es: 'Cargando logs de agentes…',
  },
  'agentLogs.empty': {
    en: 'No logs match current filters.',
    ru: 'Нет записей под текущие фильтры.',
    es: 'Ningún registro coincide con los filtros.',
  },
  'agentLogs.emptyHintAgent': {
    en: 'Try clearing search/errors for "{agent}".',
    ru: 'Очистите поиск или фильтр ошибок для «{agent}».',
    es: 'Prueba a limpiar búsqueda/errores para «{agent}».',
  },
  'agentLogs.emptyHintGeneric': {
    en: 'Try clearing filters or refresh.',
    ru: 'Сбросьте фильтры или обновите.',
    es: 'Prueba a limpiar filtros o actualizar.',
  },
};
