// The people's pages at /tools/: five free checks, rendered on the server so a search engine
// reads the whole page, in five languages with hreflang alternates. The page's own script
// (assets/tools.js) only sends the form and draws the answer; everything else is HTML.
//
// The chrome borrows the hub's stylesheet and fonts from the same origin (/assets/site.css,
// /assets/fonts/fonts.css), so these pages look like the rest of modelmarket.dev and follow it
// when the hub's design changes.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { priceOf } from "../x402.js";
import { EXAMPLES } from "./examples.js";
import { HTML_LANG, LANGS, OG_LOCALE, STRINGS } from "./i18n/index.js";

export const TOOL_IDS = ["tool-list-cost", "x402-check", "mcp-diff", "warden-scan", "histor-check"];
/** Services that also have a free A2MCP door for agents (src/services.js). */
const FREE_FOR_AGENTS = new Set(["warden-scan", "histor-check", "tool-list-cost"]);
/** Services with no paid x402 twin: the agents' section shows only the free door. */
const NOT_SOLD = new Set(["tool-list-cost"]);

const asset = (name) => {
  const body = readFileSync(new URL(`./assets/${name}`, import.meta.url));
  return { body, version: createHash("sha256").update(body).digest("hex").slice(0, 12) };
};
export const ASSETS = {
  "tools.css": { ...asset("tools.css"), type: "text/css; charset=utf-8" },
  "tools.js": { ...asset("tools.js"), type: "text/javascript; charset=utf-8" },
  "icon.png": { ...asset("icon.png"), type: "image/png" },
};

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC[c]);
/** JSON safe inside a <script> data block: no tag can close it, no line separator breaks it. */
const jsonBlock = (value) => JSON.stringify(value)
  .replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026")
  .replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");

/** Path of a page: English at /tools/…, the others under /tools/<lang>/…. */
export function pathFor(lang, id = "") {
  const prefix = lang === "en" ? "/tools/" : `/tools/${lang}/`;
  return prefix + (id || "");
}

/** The README line the tool-list-cost page offers; the page's answer fills in the real server. */
export const BADGE_MD = "![tool list](https://img.shields.io/endpoint?url=https%3A%2F%2Fmodelmarket.dev%2Ftools%2Fbadge%2Ftool-list-cost%3Fserver%3Dnpm%3Ayour-package)";

const CURL_TOOLS_LIST = [
  "curl -s https://mcp.example.com/mcp \\",
  "  -H 'content-type: application/json' \\",
  "  -H 'accept: application/json, text/event-stream' \\",
  "  -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}'",
].join("\n");

function head({ lang, title, description, path, origin, alternates, jsonLd, verification }) {
  const canonical = origin + path;
  const links = alternates.map(([l, p]) =>
    `<link rel="alternate" hreflang="${HTML_LANG[l]}" href="${esc(origin + p)}">`).join("");
  return `<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${esc(canonical)}">
${links}<link rel="alternate" hreflang="x-default" href="${esc(origin + alternates[0][1])}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="modelmarket.dev">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${esc(canonical)}">
<meta property="og:locale" content="${OG_LOCALE[lang]}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#02030a">${verification ? `
<meta name="google-site-verification" content="${esc(verification)}">` : ""}
<link rel="icon" type="image/png" href="/tools/assets/icon.png?v=${ASSETS["icon.png"].version}">
<link rel="stylesheet" href="/assets/fonts/fonts.css">
<link rel="stylesheet" href="/assets/site.css">
<link rel="stylesheet" href="/tools/assets/tools.css?v=${ASSETS["tools.css"].version}">
<script type="application/ld+json">${jsonBlock(jsonLd)}</script>`;
}

function nav(lang, alternates) {
  const t = STRINGS[lang];
  const current = alternates.find(([l]) => l === lang);
  const options = alternates.map(([l, p]) =>
    `<li><a href="${esc(p)}" hreflang="${HTML_LANG[l]}" lang="${HTML_LANG[l]}"${l === lang ? ' aria-current="true"' : ""}>${esc(STRINGS[l].name)}</a></li>`).join("");
  return `<nav><div class="nav-inner">
<a class="brand" href="/"><span class="core"></span> modelmarket.dev</a>
<div class="nav-links">
<a class="nav-live" href="/"><span class="pip"></span> Live</a>
<a href="/start">Start</a>
<a href="/developers">Developers</a>
<a href="${esc(pathFor(lang))}" class="on">${esc(t.site.tools)}</a>
</div>
<details class="lang-menu"><summary aria-label="${esc(t.site.language)}">${esc(current ? STRINGS[lang].name : lang)}</summary><ul>${options}</ul></details>
</div></nav>`;
}

function footer(lang) {
  const t = STRINGS[lang];
  return `<footer>
<div>${esc(t.site.footer)}</div>
<div><a href="/developers">API</a> · <a href="https://histor.modelmarket.dev/" rel="noopener">HISTOR</a> · <a href="https://www.npmjs.com/package/@aimarket/warden" rel="noopener">WARDEN</a> · <a href="/x402/openapi.json">x402 OpenAPI</a></div>
</footer>`;
}

export function page({ lang, tool = "", title, description, path, origin, verification = "", alternates, jsonLd, body, data }) {
  const t = STRINGS[lang];
  return `<!doctype html>
<html lang="${HTML_LANG[lang]}">
<head>
${head({ lang, title, description, path, origin, alternates, jsonLd, verification })}
<script src="/tools/assets/tools.js?v=${ASSETS["tools.js"].version}" defer></script>
</head>
<body class="tools-page"${tool ? ` data-tool="${esc(tool)}"` : ""}>
<a class="skip" href="#main">${esc(t.site.skip)}</a>
<div class="nebula"></div><div class="scan"></div><div class="vignette"></div>
${nav(lang, alternates)}
<main class="shell" id="main">
${body}
</main>
${footer(lang)}
${data ? `<script type="application/json" id="tool-data">${jsonBlock(data)}</script>` : ""}
</body>
</html>
`;
}

const crumbs = (origin, items) => ({
  "@type": "BreadcrumbList",
  itemListElement: items.map(([name, url], i) => ({ "@type": "ListItem", position: i + 1, name, item: origin + url })),
});

export function renderIndex(lang, { origin, verification = "" }) {
  const t = STRINGS[lang];
  const alternates = LANGS.map((l) => [l, pathFor(l)]);
  const cards = TOOL_IDS.map((id) => {
    const tt = t.tools[id];
    return `<article class="card tool-card">
<span class="pill free">${esc(t.ui.free.split("·")[0].trim())}</span>
<h2><a href="${esc(pathFor(lang, id))}">${esc(tt.name)}</a></h2>
<p>${esc(tt.card)}</p>
<p class="pastes"><span>${esc(t.ui.paste)}:</span> ${esc(tt.pastes)}</p>
<a class="btn" href="${esc(pathFor(lang, id))}">${esc(t.ui.open)} →</a>
</article>`;
  }).join("\n");
  const how = t.index.how.map(([h, p]) => `<div class="card"><h3>${esc(h)}</h3><p>${esc(p)}</p></div>`).join("");
  const body = `<header class="hero">
<span class="eyebrow">${esc(t.index.eyebrow)}</span>
<h1><span class="grad">${esc(t.index.h1)}</span></h1>
<p class="tagline">${esc(t.index.lead)}</p>
</header>
<section class="tool-grid" aria-label="${esc(t.site.tools)}">
${cards}
</section>
<section class="section">
<h2 class="section-title">${esc(t.index.howTitle)}</h2>
<div class="grid how-grid">${how}</div>
</section>`;
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "CollectionPage", name: t.index.title, description: t.index.description, url: origin + pathFor(lang),
        inLanguage: HTML_LANG[lang], isPartOf: { "@type": "WebSite", name: "modelmarket.dev", url: origin + "/" },
        mainEntity: { "@type": "ItemList", itemListElement: TOOL_IDS.map((id, i) => ({
          "@type": "ListItem", position: i + 1, url: origin + pathFor(lang, id), name: t.tools[id].name })) } },
      crumbs(origin, [["modelmarket.dev", "/"], [t.site.tools, pathFor(lang)]]),
    ],
  };
  return page({ lang, title: `${t.index.title} · modelmarket.dev`, description: t.index.description,
                path: pathFor(lang), origin, verification, alternates, jsonLd, body });
}

function field(id, name, f, { rows = 7, input = false } = {}) {
  const control = input
    ? `<input id="f-${name}" name="${name}" type="text" inputmode="url" autocomplete="off" spellcheck="false" aria-describedby="h-${name}">`
    : `<textarea id="f-${name}" name="${name}" rows="${rows}" autocomplete="off" spellcheck="false" aria-describedby="h-${name}"></textarea>`;
  return `<div class="field">
<label for="f-${name}">${esc(f.label)}</label>
${control}
<p class="hint" id="h-${name}">${esc(f.hint)}</p>
</div>`;
}

function formFor(id, tt) {
  const f = tt.fields;
  switch (id) {
    case "x402-check":
      return field(id, "payment", f.payment, { rows: 6 }) + field(id, "requirements", f.requirements, { rows: 5 });
    case "mcp-diff":
      return `<div class="field-pair">${field(id, "old", f.old, { rows: 12 })}${field(id, "new", f.new, { rows: 12 })}</div>`;
    case "warden-scan":
      return field(id, "tools", f.tools, { rows: 12 });
    case "tool-list-cost":
      return field(id, "server", f.server, { input: true }) + field(id, "tools", f.tools, { rows: 8 });
    default:
      return field(id, "query", f.query, { input: true });
  }
}

function howTo(id, tt) {
  if (id === "mcp-diff") {
    return `<section class="section"><h2 class="section-title">${esc(tt.howToTitle)}</h2>
<p class="section-note">${esc(tt.howTo)}</p><pre><code>${esc(CURL_TOOLS_LIST)}</code></pre></section>`;
  }
  if (id === "tool-list-cost") {
    return `<section class="section"><h2 class="section-title">${esc(tt.howToTitle)}</h2>
<p class="section-note">${esc(tt.howTo)}</p><pre><code>${esc(BADGE_MD)}</code></pre></section>`;
  }
  if (id === "warden-scan") {
    return `<section class="section"><h2 class="section-title">${esc(tt.howToTitle)}</h2>
<p class="section-note">${esc(tt.howTo)}</p><pre><code>npx -y @aimarket/warden scan</code></pre></section>`;
  }
  return "";
}

function agents(lang, id, origin) {
  const t = STRINGS[lang];
  const price = priceOf(id);
  const free = FREE_FOR_AGENTS.has(id)
    ? `<p class="section-note">${esc(t.ui.agentsFree)}</p><pre><code>POST ${esc(origin)}/a2mcp/${id}</code></pre>` : "";
  if (NOT_SOLD.has(id)) {
    return `<section class="section agents" aria-labelledby="agents-h">
<h2 class="section-title" id="agents-h">${esc(t.ui.agentsFreeTitle)}</h2>
${free}
</section>`;
  }
  return `<section class="section agents" aria-labelledby="agents-h">
<h2 class="section-title" id="agents-h">${esc(t.ui.agentsTitle)}</h2>
<p class="section-note">${esc(t.ui.agentsLead.replace("{price}", price))}</p>
<pre><code>POST ${esc(origin)}/x402/${id}</code></pre>
<p class="section-note">${esc(t.ui.agentsMore)}</p>
${free}
</section>`;
}

export function renderTool(lang, id, { origin, verification = "" }) {
  const t = STRINGS[lang];
  const tt = t.tools[id];
  const alternates = LANGS.map((l) => [l, pathFor(l, id)]);
  const checks = tt.checks.map((c) => `<li>${esc(c)}</li>`).join("");
  const faq = tt.faq.map(([q, a]) => `<details class="faq"><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join("");
  const others = TOOL_IDS.filter((o) => o !== id).map((o) =>
    `<a class="card other" href="${esc(pathFor(lang, o))}"><h3>${esc(t.tools[o].name)}</h3><p>${esc(t.tools[o].card)}</p></a>`).join("");
  const body = `<header class="hero">
<span class="eyebrow">${esc(tt.eyebrow)}</span>
<h1><span class="grad">${esc(tt.h1)}</span></h1>
<p class="tagline">${esc(tt.lead)}</p>
<p class="free-line"><span class="pill free">${esc(t.ui.free)}</span></p>
</header>
<form id="check" class="tool-form" novalidate>
${formFor(id, tt)}
<div class="actions">
<button type="submit" class="btn" id="run">${esc(t.ui.run)}</button>
<button type="button" class="btn btn-ghost" id="example">${esc(t.ui.example)}</button>
<button type="button" class="btn btn-ghost" id="clear">${esc(t.ui.clear)}</button>
<span class="kbd">${esc(t.ui.shortcut)}</span>
</div>
<p class="example-note" id="example-note" hidden>${esc(tt.exampleNote)}</p>
</form>
<section id="result" class="result" aria-live="polite" tabindex="-1" hidden></section>
<noscript><p class="section-note">${esc(t.ui.noscript)} <code>${esc(origin)}/tools/api/${id}</code></p></noscript>
<section class="section split">
<div><h2 class="section-title">${esc(t.ui.whatChecks)}</h2><ul class="checks">${checks}</ul></div>
<div><h2 class="section-title">${esc(t.ui.notChecked)}</h2><p class="section-note">${esc(tt.notChecked)}</p>
<h2 class="section-title">${esc(t.ui.privacy)}</h2><p class="section-note">${esc(tt.privacy)}</p></div>
</section>
${howTo(id, tt)}
${agents(lang, id, origin)}
<section class="section"><h2 class="section-title">${esc(t.ui.faq)}</h2>${faq}</section>
<section class="section"><h2 class="section-title">${esc(t.ui.others)}</h2><div class="grid others">${others}</div></section>`;
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "WebApplication", name: tt.name, headline: tt.h1, description: tt.description,
        url: origin + pathFor(lang, id), inLanguage: HTML_LANG[lang], applicationCategory: "DeveloperApplication",
        operatingSystem: "Any", isAccessibleForFree: true, browserRequirements: "Requires JavaScript",
        publisher: { "@type": "Organization", name: "modelmarket.dev", url: origin + "/" } },
      { "@type": "FAQPage", mainEntity: tt.faq.map(([q, a]) => ({
          "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })) },
      crumbs(origin, [["modelmarket.dev", "/"], [t.site.tools, pathFor(lang)], [tt.name, pathFor(lang, id)]]),
    ],
  };
  const data = { tool: id, lang, api: `/tools/api/${id}`, ui: t.ui, labels: tt.labels, example: EXAMPLES[id] };
  return page({ lang, tool: id, title: `${tt.title} · modelmarket.dev`, description: tt.description,
                path: pathFor(lang, id), origin, verification, alternates, jsonLd, body, data });
}

export function renderNotFound(lang, { origin }) {
  const t = STRINGS[lang];
  const links = TOOL_IDS.map((id) => `<li><a href="${esc(pathFor(lang, id))}">${esc(t.tools[id].name)}</a></li>`).join("");
  const body = `<header class="hero"><h1><span class="grad">404</span></h1>
<p class="tagline"><a href="${esc(pathFor(lang))}">${esc(t.index.title)}</a></p></header><ul class="checks">${links}</ul>`;
  return page({ lang, title: `404 · ${t.index.title}`, description: t.index.description, path: pathFor(lang), origin,
                alternates: LANGS.map((l) => [l, pathFor(l)]), jsonLd: { "@context": "https://schema.org", "@type": "WebPage" }, body });
}

export function sitemap(origin) {
  const urls = [];
  for (const id of ["", ...TOOL_IDS]) {
    const alts = LANGS.map((l) =>
      `<xhtml:link rel="alternate" hreflang="${HTML_LANG[l]}" href="${esc(origin + pathFor(l, id))}"/>`).join("");
    for (const l of LANGS) urls.push(`<url><loc>${esc(origin + pathFor(l, id))}</loc>${alts}</url>`);
  }
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
${urls.join("\n")}
</urlset>
`;
}

/** modelmarket.dev had no robots.txt at all; this one changes nothing about crawling and names the sitemap. */
export function robots(origin) {
  return `User-agent: *\nAllow: /\n\nSitemap: ${origin}/tools/sitemap.xml\n`;
}
