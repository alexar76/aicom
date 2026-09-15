import type { MarketingLocale } from './marketing';

export type FactoryIqStrings = {
  pageTitle: string;
  eyebrow: string;
  subtitle: string;
  livePulse: string;
  unavailable: string;
  heroIqLabel: string;
  buildsLiveFrozen: (live: number, frozen: number) => string;
  learningCurve: string;
  payingOff: (gap: string) => string;
  notPayingOff: string;
  noBuildsYet: string;
  liveMean: string;
  frozenControl: string;
  evTrend: string;
  evTrendHint: string;
  shipRate: string;
  costPerShip: string;
  activeRules: string;
  meanLift: (n: string) => string;
  swarmTitle: string;
  swarmSubtitle: string;
  swarmNodes: { role: string; task: string }[];
  playbookTitle: string;
  playbookEmpty: string;
  calibration: (err: string, samples: number) => string;
  backHome: string;
  chartLive: string;
  chartControl: string;
  chartEvPerBuild: string;
  gatekeeper: string;
  gatekeeperHint: string;
  modelsEvaluated: string;
};

const EN: FactoryIqStrings = {
  pageTitle: 'Factory IQ',
  eyebrow: 'Self-learning autonomous factory',
  subtitle:
    'Swarm AI models score every build. This dashboard shows realized Expected Value per build, the distilled playbook, and how well the surrogate gatekeeper is calibrated — one number that should climb as the factory learns.',
  livePulse: 'Live · refreshes every 15s',
  unavailable: 'Analytics unavailable right now.',
  heroIqLabel: 'Factory IQ',
  buildsLiveFrozen: (live, frozen) => `${live} live · ${frozen} frozen-control builds`,
  learningCurve: 'Learning curve — realized EV / build',
  payingOff: (gap) => `+${gap} vs control`,
  notPayingOff: 'not yet paying off',
  noBuildsYet: 'No builds yet',
  liveMean: 'live mean',
  frozenControl: 'frozen control',
  evTrend: 'EV trend',
  evTrendHint: '2nd half vs 1st',
  shipRate: 'Ship rate',
  costPerShip: 'Cost / ship',
  activeRules: 'Active rules',
  meanLift: (n) => `mean lift ${n}`,
  swarmTitle: 'Swarm intelligence orbit',
  swarmSubtitle: 'Specialist models route, score, and gate each pipeline stage — learning loops back into the playbook.',
  swarmNodes: [
    { role: 'PM', task: 'Spec & scope' },
    { role: 'Architect', task: 'System design' },
    { role: 'Developer', task: 'Code gen' },
    { role: 'QA', task: 'Quality gates' },
    { role: 'Surrogate', task: 'EV scoring' },
    { role: 'Evolution', task: 'Playbook distill' },
  ],
  playbookTitle: 'Validated playbook — what the factory learned',
  playbookEmpty: 'No validated rules yet — the factory needs a few more builds to distill its first lesson.',
  calibration: (err, samples) =>
    `Surrogate calibration error: ${err} over ${samples} decisions (lower = more trustworthy gatekeeper).`,
  backHome: '← Back to homepage',
  chartLive: 'Live cohort',
  chartControl: 'Frozen control',
  chartEvPerBuild: 'EV per build',
  gatekeeper: 'Gatekeeper calibration',
  gatekeeperHint: 'How well predicted EV matches outcomes',
  modelsEvaluated: 'Models in swarm',
};

const RU: FactoryIqStrings = {
  pageTitle: 'Factory IQ',
  eyebrow: 'Самообучающаяся автономная фабрика',
  subtitle:
    'Рой AI-моделей оценивает каждую сборку. Здесь — реализованный Expected Value на билд, дистиллированный playbook и калибровка суррогатного gatekeeper. Главное число должно расти по мере обучения фабрики.',
  livePulse: 'Live · обновление каждые 15 с',
  unavailable: 'Аналитика сейчас недоступна.',
  heroIqLabel: 'Factory IQ',
  buildsLiveFrozen: (live, frozen) => `${live} live · ${frozen} frozen-control сборок`,
  learningCurve: 'Кривая обучения — реализованный EV / билд',
  payingOff: (gap) => `+${gap} vs контроль`,
  notPayingOff: 'ещё не окупается',
  noBuildsYet: 'Сборок пока нет',
  liveMean: 'live среднее',
  frozenControl: 'frozen контроль',
  evTrend: 'Тренд EV',
  evTrendHint: '2-я половина vs 1-я',
  shipRate: 'Ship rate',
  costPerShip: 'Стоимость / ship',
  activeRules: 'Активные правила',
  meanLift: (n) => `средний lift ${n}`,
  swarmTitle: 'Орбита роевого интеллекта',
  swarmSubtitle:
    'Специализированные модели маршрутизируют, оценивают и гейтят каждый этап пайплайна — обучение возвращается в playbook.',
  swarmNodes: [
    { role: 'PM', task: 'Спека и scope' },
    { role: 'Architect', task: 'Архитектура' },
    { role: 'Developer', task: 'Генерация кода' },
    { role: 'QA', task: 'Quality gates' },
    { role: 'Surrogate', task: 'Скоринг EV' },
    { role: 'Evolution', task: 'Дистилляция playbook' },
  ],
  playbookTitle: 'Валидированный playbook — чему научилась фабрика',
  playbookEmpty: 'Правил пока нет — нужно ещё несколько сборок для первого урока.',
  calibration: (err, samples) =>
    `Ошибка калибровки суррогата: ${err} на ${samples} решениях (меньше = надёжнее gatekeeper).`,
  backHome: '← На главную',
  chartLive: 'Live когорта',
  chartControl: 'Frozen контроль',
  chartEvPerBuild: 'EV на билд',
  gatekeeper: 'Калибровка gatekeeper',
  gatekeeperHint: 'Насколько предсказанный EV совпадает с исходом',
  modelsEvaluated: 'Моделей в рое',
};

const ES: FactoryIqStrings = {
  pageTitle: 'Factory IQ',
  eyebrow: 'Fábrica autónoma autoaprendizaje',
  subtitle:
    'Un enjambre de modelos IA puntúa cada build. Aquí verá el Expected Value realizado por build, el playbook destilado y la calibración del gatekeeper sustituto — un número que debe subir mientras la fábrica aprende.',
  livePulse: 'En vivo · actualiza cada 15 s',
  unavailable: 'Analítica no disponible ahora.',
  heroIqLabel: 'Factory IQ',
  buildsLiveFrozen: (live, frozen) => `${live} live · ${frozen} builds control congelado`,
  learningCurve: 'Curva de aprendizaje — EV realizado / build',
  payingOff: (gap) => `+${gap} vs control`,
  notPayingOff: 'aún no compensa',
  noBuildsYet: 'Sin builds aún',
  liveMean: 'media live',
  frozenControl: 'control congelado',
  evTrend: 'Tendencia EV',
  evTrendHint: '2ª mitad vs 1ª',
  shipRate: 'Tasa de ship',
  costPerShip: 'Coste / ship',
  activeRules: 'Reglas activas',
  meanLift: (n) => `lift medio ${n}`,
  swarmTitle: 'Órbita de inteligencia enjambre',
  swarmSubtitle:
    'Modelos especialistas enrutan, puntúan y filtran cada etapa del pipeline — el aprendizaje vuelve al playbook.',
  swarmNodes: [
    { role: 'PM', task: 'Spec y alcance' },
    { role: 'Architect', task: 'Diseño sistema' },
    { role: 'Developer', task: 'Gen. código' },
    { role: 'QA', task: 'Quality gates' },
    { role: 'Surrogate', task: 'Scoring EV' },
    { role: 'Evolution', task: 'Destilar playbook' },
  ],
  playbookTitle: 'Playbook validado — lo que aprendió la fábrica',
  playbookEmpty: 'Sin reglas validadas — hacen falta más builds para la primera lección.',
  calibration: (err, samples) =>
    `Error de calibración sustituta: ${err} en ${samples} decisiones (menor = gatekeeper más fiable).`,
  backHome: '← Volver al inicio',
  chartLive: 'Cohorte live',
  chartControl: 'Control congelado',
  chartEvPerBuild: 'EV por build',
  gatekeeper: 'Calibración gatekeeper',
  gatekeeperHint: 'Qué tan bien el EV previsto coincide con el resultado',
  modelsEvaluated: 'Modelos en enjambre',
};

export function getFactoryIqStrings(locale: MarketingLocale): FactoryIqStrings {
  if (locale === 'ru') return RU;
  if (locale === 'es') return ES;
  return EN;
}
