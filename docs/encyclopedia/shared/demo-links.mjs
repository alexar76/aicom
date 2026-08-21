/** Canonical live-demo URLs for encyclopedia cross-links. */
export const ORACLE_PORTAL = 'https://oracles.modelmarket.dev';

export const DEMO = {
  oraclePortal: ORACLE_PORTAL,
  platonUmbral: 'https://oracles.modelmarket.dev/platon/umbral',
  lottery: 'https://lottery.modelmarket.dev',
  alienMonitor: 'https://magic-ai-factory.com/monitor/',
  ecosystem: 'https://modeldev.modelmarket.dev',
  factory: 'https://magic-ai-factory.com',
  factoryIq: 'https://magic-ai-factory.com/iq',
  hub: 'https://modelmarket.dev',
  pulse: 'https://magic-ai-factory.com/pulse/',
  argus: 'https://magic-ai-factory.com/argus/',
  atlas: 'https://atlas.modelmarket.dev/',
  atlasLanding: 'https://alexar76.github.io/atlas/',
  skopos: 'https://skopos.modelmarket.dev',
  gaia: 'https://iot.modelmarket.dev/',
  metis: 'https://metis.modelmarket.dev',
  helios: 'https://alexar76.github.io/helios/',
  dioscuri: 'https://alexar76.github.io/dioscuri/',
  mcp: 'https://modeldev.modelmarket.dev/mcp/',
  bridges: 'https://modeldev.modelmarket.dev/bridges/',
};

/** Platon is the only oracle with a separate full cockpit app. */
export const ORACLE_COCKPITS = {
  platon: DEMO.platonUmbral,
};

export function oracleSlug(name) {
  return String(name).trim().toLowerCase();
}

export function oracleSceneUrl(nameOrSlug) {
  const slug = oracleSlug(nameOrSlug);
  return `${ORACLE_PORTAL}/?o=${encodeURIComponent(slug)}`;
}

export function oracleCockpitUrl(nameOrSlug) {
  return ORACLE_COCKPITS[oracleSlug(nameOrSlug)];
}

export const ORACLE_GRID_COPY = {
  en: {
    hint: 'Each card opens the live 3D scene on the oracle portal.',
    scene: '3D scene ↗',
    cockpit: 'UMBRAL cave ↗',
    stripTitle: 'Featured oracle demos',
    portal: 'Family portal — all 17 oracles',
    umbral: 'Platon UMBRAL — live cockpit',
    lottery: 'Agent Lottery — Chronos × Platon × Lumen',
  },
  ru: {
    hint: 'Каждая карточка открывает живую 3D-сцену на портале оракулов.',
    scene: '3D-сцена ↗',
    cockpit: 'UMBRAL-пещера ↗',
    stripTitle: 'Избранные демо оракулов',
    portal: 'Портал семейства — все 17 оракулов',
    umbral: 'Platon UMBRAL — живой cockpit',
    lottery: 'Agent Lottery — Chronos × Platon × Lumen',
  },
  es: {
    hint: 'Cada tarjeta abre la escena 3D en vivo en el portal de oráculos.',
    scene: 'Escena 3D ↗',
    cockpit: 'Cueva UMBRAL ↗',
    stripTitle: 'Demos destacados de oráculos',
    portal: 'Portal familiar — los 17 oráculos',
    umbral: 'Platon UMBRAL — cockpit en vivo',
    lottery: 'Agent Lottery — Chronos × Platon × Lumen',
  },
  fr: {
    hint: 'Chaque carte ouvre la scène 3D en direct sur le portail des oracles.',
    scene: 'Scène 3D ↗',
    cockpit: 'Grotte UMBRAL ↗',
    stripTitle: "Démos d'oracles en vedette",
    portal: 'Portail de la famille — les 17 oracles',
    umbral: 'Platon UMBRAL — cockpit en direct',
    lottery: 'Agent Lottery — Chronos × Platon × Lumen',
  },
  zh: {
    hint: '每张卡片都会在预言机门户上打开实时 3D 场景。',
    scene: '3D 场景 ↗',
    cockpit: 'UMBRAL 洞窟 ↗',
    stripTitle: '精选预言机演示',
    portal: '家族门户——全部 17 个预言机',
    umbral: 'Platon UMBRAL——实时 cockpit',
    lottery: 'Agent Lottery——Chronos × Platon × Lumen',
  },
};

export const MONITOR_COPY = {
  en: 'Open Alien Monitor (live 3D graph) ↗',
  ru: 'Открыть Alien Monitor (живой 3D-граф) ↗',
  es: 'Abrir Alien Monitor (grafo 3D en vivo) ↗',
  fr: 'Ouvrir Alien Monitor (graphe 3D en direct) ↗',
  zh: '打开 Alien Monitor(实时 3D 图谱)↗',
};

/** Longest domains first — avoid partial replacements. */
export const BARE_DOMAIN_LINKS = [
  ['atlas.modelmarket.dev', DEMO.atlas],
  ['skopos.modelmarket.dev', DEMO.skopos],
  ['iot.modelmarket.dev', DEMO.gaia],
  ['gaia.modelmarket.dev', DEMO.gaia],
  ['metis.modelmarket.dev', DEMO.metis],
  ['modeldev.modelmarket.dev', DEMO.ecosystem],
  ['oracles.modelmarket.dev', DEMO.oraclePortal],
  ['lottery.modelmarket.dev', DEMO.lottery],
  ['magic-ai-factory.com', DEMO.factory],
  ['modelmarket.dev', DEMO.hub],
];

/** Named demo surfaces without a bare domain in prose. */
export const PHRASE_LINKS = [
  ['Alien Monitor', DEMO.alienMonitor],
  ['Factory IQ', DEMO.factoryIq],
  ['ATLAS Analyst', DEMO.atlas],
  ['ATLAS', DEMO.atlas],
  ['SKOPOS', DEMO.skopos],
  ['GAIA', DEMO.gaia],
  ['Metis', DEMO.metis],
  ['HELIOS', DEMO.helios],
  ['DIOSCURI', DEMO.dioscuri],
  ['портал оракулов', DEMO.oraclePortal],
  ['portal oráculos', DEMO.oraclePortal],
  ['oracles portal', DEMO.oraclePortal],
  ['витрина Factory', DEMO.factory],
  ['vitrina Factory', DEMO.factory],
  ['Factory storefront', DEMO.factory],
  ['ecosystem landing', DEMO.ecosystem],
];

/** Public Factory routes written as `/path` in backticks — link to live demo. */
export const FACTORY_PATH_LINKS = [
  ['/iq', DEMO.factoryIq],
  ['/monitor', DEMO.alienMonitor],
  ['/pulse', DEMO.pulse],
  ['/argus', DEMO.argus],
  ['/admin', `${DEMO.factory}/admin`],
];

function mdLink(label, url) {
  return `[${label}](${url})`;
}

/** Turn bare https URLs, domains, and known demo phrases into markdown links. */
export function autoLinkDemos(text) {
  let s = String(text ?? '');
  if (!s) return s;

  const tokens = [];

  function stash(html) {
    const key = `\x00L${tokens.length}\x00`;
    tokens.push(html);
    return key;
  }

  s = s.replace(/(?<!\]\()https:\/\/[^\s)<>,]+/g, (url) =>
    stash(mdLink(url.replace(/^https:\/\//, ''), url))
  );

  for (const [domain, url] of BARE_DOMAIN_LINKS) {
    const re = new RegExp(`(?<!\\[)(?<!\`)\\b${domain.replace(/\./g, '\\.')}\\b`, 'gi');
    s = s.replace(re, (match) => stash(mdLink(match, url)));
  }

  for (const [path, url] of FACTORY_PATH_LINKS) {
    const escPath = path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    s = s.replace(new RegExp(`\`${escPath}\``, 'g'), () => stash(mdLink(path, url)));
  }

  for (const [phrase, url] of PHRASE_LINKS) {
    const re = new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    s = s.replace(re, (match) => {
      if (s.includes(`[${match}]`)) return match;
      return stash(mdLink(match, url));
    });
  }

  return s.replace(/\x00L(\d+)\x00/g, (_, i) => tokens[Number(i)]);
}
