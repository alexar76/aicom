import type { I18nDict } from '../../types';

export const STANDUP_SETTINGS_DICT: I18nDict = {
  'settings.section.directorStandup': {
    en: 'Director standup — Corporate Chat',
    ru: 'Стендап Director — Corporate Chat',
    es: 'Standup del Director — Corporate Chat',
    fr: 'Standup du Director — Corporate Chat',
    zh: 'Director 站会 — Corporate Chat',
  },
  'settings.standup.intro': {
    en: 'AI Director runs a standup in Corporate Chat at the scheduled local time: plan, agent-style reports, clarifying questions. You participate as Owner (display name is configured in Corporate Chat tab). This differs from Brainstorming sessions — see docs/corporate-chat-vs-discussions.md.',
    ru: 'AI Director проводит стендап в Corporate Chat в запланированное локальное время: план, отчёты в стиле агентов, уточняющие вопросы. Вы участвуете как Owner (отображаемое имя задаётся во вкладке Corporate Chat). Это не Brainstorming — см. docs/corporate-chat-vs-discussions.md.',
    es: 'El AI Director hace un standup en Corporate Chat a la hora local programada: plan, informes estilo agente, preguntas aclaratorias. Participas como Owner (el nombre se configura en la pestaña Corporate Chat). No es lo mismo que Brainstorming — ver docs/corporate-chat-vs-discussions.md.',
    fr: 'L\'AI Director anime un standup dans Corporate Chat à l\'heure locale planifiée : plan, rapports façon agent, questions de clarification. Vous participez en tant qu\'Owner (le nom affiché se configure dans l\'onglet Corporate Chat). Cela diffère des sessions Brainstorming — voir docs/corporate-chat-vs-discussions.md.',
    zh: 'AI Director 在预定的本地时间于 Corporate Chat 中主持站会：计划、智能体风格的汇报、澄清问题。你以 Owner 身份参与（显示名称在 Corporate Chat 标签页中配置）。这与 Brainstorming 会话不同 — 见 docs/corporate-chat-vs-discussions.md。',
  },
  'settings.standup.enableDaily': {
    en: 'Enable daily standup',
    ru: 'Включить ежедневный стендап',
    es: 'Activar standup diario',
    fr: 'Activer le standup quotidien',
    zh: '启用每日站会',
  },
  'settings.standup.localTime': {
    en: 'Local time (HH:MM)',
    ru: 'Локальное время (ЧЧ:ММ)',
    es: 'Hora local (HH:MM)',
    fr: 'Heure locale (HH:MM)',
    zh: '本地时间 (HH:MM)',
  },
  'settings.standup.timezone': {
    en: 'IANA timezone',
    ru: 'Часовой пояс IANA',
    es: 'Zona horaria IANA',
    fr: 'Fuseau horaire IANA',
    zh: 'IANA 时区',
  },
  'settings.standup.saving': {
    en: 'Saving standup schedule…',
    ru: 'Сохранение расписания стендапа…',
    es: 'Guardando horario de standup…',
    fr: 'Enregistrement du planning du standup…',
    zh: '正在保存站会计划…',
  },
  'settings.standup.autosaveHint': {
    en: 'Standup schedule saves automatically a moment after you change it.',
    ru: 'Расписание стендапа сохраняется автоматически через мгновение после изменения.',
    es: 'El horario del standup se guarda solo un momento después de cambiarlo.',
    fr: 'Le planning du standup est enregistré automatiquement peu après modification.',
    zh: '站会计划在你更改后片刻自动保存。',
  },
  'settings.toast.standupSaved': {
    en: '✅ Corporate Chat / standup schedule saved',
    ru: '✅ Corporate Chat / расписание стендапа сохранено',
    es: '✅ Corporate Chat / horario de standup guardado',
    fr: '✅ Corporate Chat / planning du standup enregistré',
    zh: '✅ Corporate Chat / 站会计划已保存',
  },
  'settings.toast.standupSaveFailed': {
    en: 'Failed to save standup schedule',
    ru: 'Не удалось сохранить расписание стендапа',
    es: 'Error al guardar el horario del standup',
    fr: 'Échec de l\'enregistrement du planning du standup',
    zh: '保存站会计划失败',
  },
};
