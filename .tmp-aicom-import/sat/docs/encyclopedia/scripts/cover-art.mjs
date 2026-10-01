function coverArtSvg() {
  return `<svg class="cover-art-svg" viewBox="0 0 800 1000" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>
      <radialGradient id="nebula" cx="50%" cy="35%" r="65%">
        <stop offset="0%" stop-color="#4c1d95" stop-opacity="0.9"/>
        <stop offset="45%" stop-color="#1e1b4b" stop-opacity="0.6"/>
        <stop offset="100%" stop-color="#030014" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="planetMain" cx="38%" cy="32%" r="62%">
        <stop offset="0%" stop-color="#e9d5ff"/>
        <stop offset="35%" stop-color="#a78bfa"/>
        <stop offset="70%" stop-color="#6d28d9"/>
        <stop offset="100%" stop-color="#312e81"/>
      </radialGradient>
      <radialGradient id="planetCyan" cx="30%" cy="28%" r="60%">
        <stop offset="0%" stop-color="#cffafe"/>
        <stop offset="100%" stop-color="#0891b2"/>
      </radialGradient>
      <radialGradient id="planetGold" cx="35%" cy="30%" r="55%">
        <stop offset="0%" stop-color="#fef3c7"/>
        <stop offset="100%" stop-color="#d97706"/>
      </radialGradient>
      <linearGradient id="aurora" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#06b6d4" stop-opacity="0"/>
        <stop offset="30%" stop-color="#22d3ee" stop-opacity="0.35"/>
        <stop offset="55%" stop-color="#c084fc" stop-opacity="0.45"/>
        <stop offset="80%" stop-color="#f472b6" stop-opacity="0.3"/>
        <stop offset="100%" stop-color="#fbbf24" stop-opacity="0"/>
      </linearGradient>
      <filter id="glow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <rect width="800" height="1000" fill="#030014"/>
    <rect width="800" height="1000" fill="url(#nebula)"/>
    <ellipse cx="400" cy="280" rx="340" ry="90" fill="url(#aurora)" opacity="0.8"/>
    ${[
      [120,180,1.2,'#fef3c7'],[680,120,0.8,'#67e8f9'],[720,420,1,'#fcd34d'],[90,520,0.7,'#f9a8d4'],
      [650,680,1.1,'#c4b5fd'],[180,780,0.9,'#fef3c7'],[540,860,0.6,'#67e8f9'],[320,140,0.5,'#fff'],
      [480,720,0.8,'#fbbf24'],[760,280,0.7,'#a5f3fc'],[60,340,0.9,'#e9d5ff'],[400,90,1.3,'#fef3c7']
    ].map(([x,y,s,c]) => `<circle cx="${x}" cy="${y}" r="${s*2}" fill="${c}" opacity="0.85"/>`).join('')}
    <ellipse cx="400" cy="520" rx="280" ry="42" fill="none" stroke="#c4b5fd" stroke-width="1.5" opacity="0.25" transform="rotate(-12 400 520)"/>
    <ellipse cx="400" cy="520" rx="220" ry="32" fill="none" stroke="#67e8f9" stroke-width="1" opacity="0.2" transform="rotate(18 400 520)"/>
    <circle cx="400" cy="380" r="95" fill="url(#planetMain)" filter="url(#glow)"/>
    <circle cx="400" cy="380" r="95" fill="none" stroke="#e9d5ff" stroke-width="1.5" opacity="0.35"/>
    <circle cx="155" cy="290" r="28" fill="url(#planetCyan)"/>
    <circle cx="620" cy="250" r="22" fill="url(#planetGold)"/>
    <circle cx="680" cy="480" r="16" fill="#831843" stroke="#f9a8d4" stroke-width="1.5"/>
    <circle cx="130" cy="600" r="14" fill="#14532d" stroke="#6ee7b7" stroke-width="1.5"/>
  </svg>`;
}

function splitCoverTitle(title) {
  const t = String(title).trim();
  if (/\sAICOM\s*$/i.test(t)) {
    return [t.replace(/\s*AICOM\s*$/i, '').trim(), 'AICOM'];
  }
  if (/^AICOM\s+/i.test(t)) {
    return ['AICOM', t.replace(/^AICOM\s+/i, '').trim()];
  }
  const parts = t.split(/\s+—\s+|\s+-\s+/);
  return [parts[0] || t, parts[1] || ''];
}

const ORB_LABELS = {
  en: ['Factory', 'Hub', 'Oracles ×17', 'Base', 'ARGUS'],
  ru: ['Factory', 'Hub', 'Оракулы ×17', 'Base', 'ARGUS'],
  es: ['Factory', 'Hub', 'Oráculos ×17', 'Base', 'ARGUS'],
  fr: ['Factory', 'Hub', 'Oracles ×17', 'Base', 'ARGUS'],
  zh: ['Factory', 'Hub', '预言机 ×17', 'Base', 'ARGUS'],
};

function renderCover(c, langLinks, esc, locale = 'en') {
  const [line1, line2] = splitCoverTitle(c.meta.title);
  const orbs = ORB_LABELS[locale] || ORB_LABELS.en;
  const orbClasses = ['purple', 'cyan', 'pink', 'gold', 'green'];
  const sigils = ['✦', '◇', '✧', '◈', '✦'];
  return `<header class="cover" id="top">
    <div class="cover-frame">
      <div class="cover-sigils top">${sigils.map((s) => `<span>${s}</span>`).join('')}</div>
      <div class="cover-scene">${coverArtSvg()}</div>
      <div class="cover-inner">
        <p class="cover-kicker">AICOM</p>
        <p class="edition">${esc(c.meta.edition)}</p>
        <h1 class="cover-title">
          <span class="cover-title-line">${esc(line1)}</span>
          ${line2 ? `<span class="cover-title-sub">${esc(line2)}</span>` : ''}
        </h1>
        <p class="subtitle">${esc(c.meta.subtitle)}</p>
        <div class="cover-orbs" aria-hidden="true">
          ${orbs.map((label, i) => `<span class="orb ${orbClasses[i]}">${esc(label)}</span>`).join('')}
        </div>
        <nav class="lang-switch cover-nav" aria-label="Language">${langLinks}</nav>
        <p class="scroll-hint">▼ ${esc(c.meta.scrollHint)} ▼</p>
      </div>
      <div class="cover-sigils bottom">${sigils.map((s) => `<span>${s}</span>`).join('')}</div>
    </div>
  </header>`;
}

export { coverArtSvg, renderCover };
