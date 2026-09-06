# AICOM ecosystem landing

> 🌐 **English** · [Русский](docs/README.ru.md) · [Español](docs/README.es.md) · [Français](docs/README.fr.md) · [中文](docs/README.zh.md) · [Glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

> **Live site:** [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev)  
> **Documentation:** [Ecosystem knowledge base](../docs/ecosystem/knowledge-base.md) · [RU](../docs/ecosystem/knowledge-base-ru.md) · [ES](../docs/ecosystem/knowledge-base-es.md) · [FR](../docs/ecosystem/knowledge-base-fr.md) · [ZH](../docs/ecosystem/knowledge-base-zh.md) · [Whitepaper](../docs/ecosystem/whitepaper/en.md)

[![Alien Monitor — full ecosystem graph with live metrics, Capability NFT panel, and activity stream](https://github.com/alexar76/alien-monitor/blob/main/docs/screenshots/09-ecosystem-simulation.png)](https://monitor.modelmarket.dev/)

*Alien Monitor — 3D graph of Hub, Mesh, ARGUS, SDKs, plugins, and on-chain activity. [Open live →](https://monitor.modelmarket.dev/)*

A single-file, dependency-free landing page that explains the whole AICOM
ecosystem (AI-Factory, AIMarket Hub, **HEPHAESTUS** chain forge, **Oracles**, **Metis**, **aimarket-mcp** MCP gateway,
Protocol, SDKs, desktop apps, contracts) and links each part to its source and live demo.
The **`#oracles`** section embeds seventeen card-preview `.gif` loops from
[alexar76/oracles](https://github.com/alexar76/oracles). The **`#mcp`** section lists the
three Glama-indexed MCP servers (oracle-gateway, ecosystem gateway, plugins packager).
Sci-fi "Alien Monitor" look with a live animated galaxy canvas (works on mobile + desktop;
degrades to a calmer drift under `prefers-reduced-motion`).

## Preview locally

```bash
# any static server works — e.g. Node (no deps):
node -e 'import("node:http").then(async({createServer})=>{const{readFile}=await import("node:fs/promises");createServer(async(q,s)=>{let p=q.url==="/"?"/index.html":q.url;try{s.end(await readFile("ecosystem-landing"+p))}catch{s.writeHead(404);s.end()}}).listen(8743,()=>console.log("http://localhost:8743"))})'
```

Or just open `ecosystem-landing/index.html` in a browser.

## Deploy — GitHub Pages (current setup)

[`.github/workflows/pages-ecosystem.yml`](../.github/workflows/pages-ecosystem.yml)
publishes this folder to GitHub Pages on every push to `main` that touches
`ecosystem-landing/**`, `seo-landings/**`, encyclopedia, specs, courses, or oracles metadata.

The workflow **builds SEO landings first** (`./scripts/build_ecosystem_landing.sh` with
`SEO_BASE_URL=https://alexar76.github.io/aicom`), then uploads the full tree.

**One-time setup on GitHub:** repo **Settings → Pages → Build and deployment →
Source: GitHub Actions**. After the first run the site is live at
`https://alexar76.github.io/aicom/`.

### SEO sub-sites (built, not hand-edited)

| URL path | Built from |
|----------|------------|
| `/learn/` | `scripts/build_seo_landings.py` + courses |
| `/oracles/` | oracle metadata in `oracles/frontend/src/oracles.ts` |
| `/guides/` | `seo-landings/data/guides.yaml` + spec markdown |
| `/encyclopedia/` | `docs/encyclopedia/` |
| `/sitemap.xml` | auto-generated |

See [`seo-landings/README.md`](../seo-landings/README.md) for the full build/deploy contract.

### Custom domain (optional, later)

Add a `CNAME` file in this folder containing the bare domain (e.g. `aicom.dev`),
point the domain's DNS at GitHub Pages, then enable HTTPS in Settings → Pages.

### Production host (magic-ai-factory fleet)

On the server with nginx + `/var/www/modeldev.modelmarket.dev`:

```bash
# Builds SEO landings (modeldev canonical) then rsync
sudo ./scripts/deploy_ecosystem_landing.sh
```

Or build only (no rsync):

```bash
./scripts/build_ecosystem_landing.sh
./scripts/verify_seo_landings.sh
```

This also runs automatically as step **7/7** of `./scripts/deploy_ecosystem.sh`.
First-time TLS: `sudo ./scripts/setup-modeldev-ecosystem-landing.sh`.

## Notes

- **ARGUS installer** — `install` and `argus/install` are served as static files
  (`curl -fsSL https://modeldev.modelmarket.dev/install | bash`). On
  `magic-ai-factory.com`, run `sudo ./scripts/setup-argus-install.sh` on the server.
- Sub-project links point at **standalone satellite repos**
  (`github.com/alexar76/<repo>`); payment contracts remain under
  `github.com/alexar76/aicom/tree/main/contracts`.
- Both primary CTAs (Star on GitHub + Try live demo) appear in the hero and the
  closing section.
- No external JS/CSS except the Google Fonts (Orbitron / Rajdhani) and the
  YouTube thumbnail used for the social preview image. No trackers.
- `.nojekyll` disables Jekyll processing on Pages.
