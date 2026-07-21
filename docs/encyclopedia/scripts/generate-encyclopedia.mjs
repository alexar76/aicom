#!/usr/bin/env node
/**
 * Build localized HTML encyclopedia from content/*.json
 * Usage: node docs/encyclopedia/scripts/generate-encyclopedia.mjs [en|ru|es|all]
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { renderCover } from './cover-art.mjs';
import {
  DEMO,
  MONITOR_COPY,
  ORACLE_GRID_COPY,
  ORACLE_PORTAL,
  autoLinkDemos,
  oracleCockpitUrl,
  oracleSceneUrl,
  oracleSlug,
} from '../shared/demo-links.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const CONTENT_DIR = path.join(ROOT, 'content');

const LOCALES = ['en', 'ru', 'es'];

function imageDataUrl(relPath) {
  const abs = path.join(ROOT, relPath);
  if (!fs.existsSync(abs)) {
    console.warn(`[encyclopedia] missing image: ${abs}`);
    return null;
  }
  const ext = path.extname(abs).toLowerCase();
  const mime =
    { '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg' }[ext] ||
    'image/png';
  return `data:${mime};base64,${fs.readFileSync(abs).toString('base64')}`;
}

function imgTag(relPath, alt, className = '') {
  const data = imageDataUrl(relPath);
  const cls = className ? ` class="${className}"` : '';
  const src = data || `../${relPath}`;
  return `<img src="${src}" alt="${esc(alt)}"${cls} decoding="sync" />`;
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function mdInline(s) {
  const linked = autoLinkDemos(s);
  return esc(linked)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
      const external = /^https?:\/\//i.test(href);
      const cls = external ? ' class="demo-link"' : '';
      const attrs = external ? ' target="_blank" rel="noopener noreferrer"' : '';
      return `<a href="${href}"${cls}${attrs}>${label}</a>`;
    });
}

function demoLink(href, label) {
  return `<a class="demo-link" href="${href}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
}

function renderTable(headers, rows) {
  const th = headers.map((h) => `<th>${esc(h)}</th>`).join('');
  const tr = rows
    .map((row) => `<tr>${row.map((c) => `<td>${mdInline(c)}</td>`).join('')}</tr>`)
    .join('');
  return `<table class="data-table"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

function renderCards(cards) {
  return `<div class="card-grid">${cards
    .map(
      (c) => `<article class="planet-card ${c.color || 'purple'}">
        <div class="icon">${c.icon}</div>
        <h3>${esc(c.title)}</h3>
        <p>${mdInline(c.body)}</p>
        ${c.tag ? `<span class="tag">${esc(c.tag)}</span>` : ''}
      </article>`
    )
    .join('')}</div>`;
}

function renderOracles(list, locale) {
  const copy = ORACLE_GRID_COPY[locale] || ORACLE_GRID_COPY.en;
  const chips = list
    .map((o) => {
      const slug = o.slug || oracleSlug(o.name);
      const scene = oracleSceneUrl(slug);
      const cockpit = oracleCockpitUrl(slug);
      const cockpitLink = cockpit
        ? `<a class="oracle-cockpit-link" href="${cockpit}" target="_blank" rel="noopener noreferrer">${esc(copy.cockpit)}</a>`
        : '';
      return `<div class="oracle-chip-wrap">
        <a class="oracle-chip" href="${scene}" target="_blank" rel="noopener noreferrer" title="${esc(copy.scene)} — ${esc(o.name)}">
          <strong>${esc(o.name)}</strong>
          <span class="oracle-skill">${esc(o.skill)}</span>
          <span class="oracle-open">${esc(copy.scene)}</span>
        </a>
        ${cockpitLink}
      </div>`;
    })
    .join('');
  const strip = `<div class="demo-strip oracle-demo-strip">
    <h4>${esc(copy.stripTitle)}</h4>
    <div class="demo-strip-links">
      ${demoLink(DEMO.oraclePortal, copy.portal)}
      ${demoLink(DEMO.platonUmbral, copy.umbral)}
      ${demoLink(DEMO.lottery, copy.lottery)}
    </div>
  </div>`;
  return `<div class="oracle-section">
    <p class="oracle-grid-hint">${demoLink(ORACLE_PORTAL, 'oracles.modelmarket.dev')} — ${esc(copy.hint)}</p>
    <div class="oracle-grid">${chips}</div>
    ${strip}
  </div>`;
}

function renderShots(shots, locale) {
  return `<div class="screenshot-gallery">${shots
    .map((s) => {
      const rel = s.shared
        ? `assets/screenshots/shared/${s.file}`
        : `assets/screenshots/${locale}/${s.file}`;
      return `<figure class="shot">
        ${imgTag(rel, s.caption)}
        <figcaption>${esc(s.caption)}</figcaption>
      </figure>`;
    })
    .join('')}</div>`;
}

function renderFaq(groups) {
  return groups
    .map(
      (g) => `<div class="faq-group">
        <h3>${esc(g.title)}</h3>
        ${g.items
          .map(
            (item) => `<div class="faq-item">
              <p class="faq-q">${esc(item.q)}</p>
              <div class="answer">${mdInline(item.a)}</div>
            </div>`
          )
          .join('')}
      </div>`
    )
    .join('');
}

function renderEpilogue(meta, esc, mdInline) {
  const raw = meta.epilogue || '';
  const split = raw.match(/^(.*?)\s+\*\*(.+?)\*\*\s*$/s);
  const body = split
    ? `<p class="epilogue-body">${mdInline(split[1])}</p>
      <p class="epilogue-tagline">${mdInline(`**${split[2]}**`)}</p>`
    : `<p class="epilogue-body">${mdInline(raw)}</p>`;
  return `${body}
      <p class="epilogue-meta">${esc(meta.version)}</p>`;
}

function renderEcosystemDiagram(caption, esc, locale) {
  const simCaptions = {
    en: 'Alien Monitor — simulation mode with metrics & activity stream',
    ru: 'Alien Monitor — режим симуляции с метриками и потоком активности',
    es: 'Alien Monitor — modo simulación con métricas y flujo de actividad',
  };
  const simCaption = simCaptions[locale] || simCaptions.en;
  const monitorLink = demoLink(DEMO.alienMonitor, MONITOR_COPY[locale] || MONITOR_COPY.en);
  return `<div class="diagram-box diagram-hero">
    <figure class="diagram-figure">
      <a class="diagram-link" href="${DEMO.alienMonitor}" target="_blank" rel="noopener noreferrer">
        ${imgTag('assets/screenshots/shared/alien-ecosystem.png', 'AICOM ecosystem LIVE graph', 'diagram-photo')}
      </a>
      <figcaption class="diagram-caption">${esc(caption)} ${monitorLink}</figcaption>
    </figure>
    <figure class="diagram-figure">
      <a class="diagram-link" href="${DEMO.alienMonitor}" target="_blank" rel="noopener noreferrer">
        ${imgTag('assets/screenshots/shared/alien-simulation.png', 'Ecosystem simulation', 'diagram-photo')}
      </a>
      <figcaption class="diagram-caption">${esc(simCaption)} ${monitorLink}</figcaption>
    </figure>
  </div>`;
}

function invokeSvg() {
  return `<svg viewBox="0 0 900 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Invoke flow">
    <rect width="900" height="200" fill="#0a0520" rx="12"/>
    ${[
      ['Agent', 60, '#7c3aed'],
      ['Discover', 180, '#6d28d9'],
      ['Channel', 300, '#0891b2'],
      ['Invoke', 420, '#0e7490'],
      ['Receipt', 540, '#be185d'],
      ['Settle', 660, '#34d399'],
      ['USDC', 780, '#fbbf24'],
    ]
      .map(
        ([label, x, color], i, arr) => `
      <rect x="${x - 45}" y="70" width="90" height="50" rx="10" fill="${color}" opacity="0.85"/>
      <text x="${x}" y="100" text-anchor="middle" fill="#fff" font-size="11">${label}</text>
      ${i < arr.length - 1 ? `<line x1="${x + 50}" y1="95" x2="${arr[i + 1][1] - 50}" y2="95" stroke="#a89fd4" stroke-width="2" marker-end="url(#arrow)"/>` : ''}`
      )
      .join('')}
    <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#a89fd4"/></marker></defs>
  </svg>`;
}

function buildHtml(c, locale) {
  const langAttr = { en: 'en', ru: 'ru', es: 'es' }[locale];
  const langLinks = LOCALES.map(
    (l) => `<a href="../${l}/index.html" class="${l === locale ? 'active' : ''}">${l.toUpperCase()}</a>`
  ).join('');

  const chapters = c.chapters
    .map((ch, i) => {
      let body = '';
      if (ch.lead) body += `<p class="lead">${mdInline(ch.lead)}</p>`;
      if (ch.paragraphs) body += ch.paragraphs.map((p) => `<p>${mdInline(p)}</p>`).join('');
      if (ch.table) body += renderTable(ch.table.headers, ch.table.rows);
      if (ch.cards) body += renderCards(ch.cards);
      if (ch.oracles) body += renderOracles(ch.oracles, locale);
      if (ch.shots) body += renderShots(ch.shots, locale);
      if (ch.diagram === 'ecosystem') {
        body += renderEcosystemDiagram(ch.diagramCaption || '', esc, locale);
      }
      if (ch.diagram === 'invoke') {
        body += `<div class="diagram-box">${invokeSvg()}<p class="diagram-caption">${esc(ch.diagramCaption || '')}</p></div>`;
      }
      if (ch.pre) body += `<pre>${esc(ch.pre)}</pre>`;
      if (ch.faq) body += `<div class="faq-section">${renderFaq(ch.faq)}</div>`;

      return `<section class="chapter" id="ch${i + 1}">
        <div class="chapter-header">
          <span class="chapter-num">${String(i + 1).padStart(2, '0')}</span>
          <h2>${esc(ch.title)}</h2>
        </div>
        ${body}
      </section>`;
    })
    .join('\n');

  const toc = c.chapters
    .map((ch, i) => `<li><a href="#ch${i + 1}">${esc(ch.title)}</a></li>`)
    .join('');

  return `<!DOCTYPE html>
<html lang="${langAttr}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${esc(c.meta.title)}</title>
  <link rel="stylesheet" href="../shared/encyclopedia.css" />
</head>
<body>
  <div class="cosmos"></div>
  <div class="stars"></div>

  ${renderCover(c, langLinks, esc, locale)}

  <main class="wrap">
    <nav class="toc" aria-label="Contents">
      <h2>${esc(c.meta.tocTitle)}</h2>
      <ol>${toc}</ol>
    </nav>
    ${chapters}
    <footer class="epilogue">
      <div class="sigil">✦</div>
      ${renderEpilogue(c.meta, esc, mdInline)}
    </footer>
  </main>
</body>
</html>`;
}

function buildPortal() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AICOM Cosmic Encyclopedia — Choose Your Language</title>
  <link rel="stylesheet" href="shared/encyclopedia.css" />
</head>
<body>
  <div class="cosmos"></div>
  <div class="stars"></div>
  <header class="cover">
    <div class="planet-hero"></div>
    <p class="edition">AICOM · Federated Autonomous-Agent Economy</p>
    <h1>Cosmic Encyclopedia</h1>
    <p class="subtitle">A storybook for geek children of the distant future — ideology, planets, oracles, and practical magic in three tongues.</p>
    <nav class="lang-switch">
      <a href="en/index.html">English</a>
      <a href="ru/index.html">Русский</a>
      <a href="es/index.html">Español</a>
    </nav>
    <p style="margin-top:2rem;color:var(--text-dim);font-size:0.85rem;">
      PDF: <a href="pdf/aicom-encyclopedia-en.pdf">EN</a> ·
      <a href="pdf/aicom-encyclopedia-ru.pdf">RU</a> ·
      <a href="pdf/aicom-encyclopedia-es.pdf">ES</a>
    </p>
  </header>
</body>
</html>`;
}

function main() {
  const arg = process.argv[2] || 'all';
  const targets = arg === 'all' ? LOCALES : [arg];

  for (const locale of targets) {
    const src = path.join(CONTENT_DIR, `${locale}.json`);
    if (!fs.existsSync(src)) {
      console.error(`Missing ${src}`);
      process.exit(1);
    }
    const content = JSON.parse(fs.readFileSync(src, 'utf8'));
    const outDir = path.join(ROOT, locale);
    fs.mkdirSync(outDir, { recursive: true });
    const html = buildHtml(content, locale);
    fs.writeFileSync(path.join(outDir, 'index.html'), html);
    console.log(`Built ${locale}/index.html`);
  }

  if (arg === 'all' || arg === 'portal') {
    fs.writeFileSync(path.join(ROOT, 'index.html'), buildPortal());
    console.log('Built index.html portal');
  }
}

main();
