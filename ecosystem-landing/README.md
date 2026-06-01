# AICOM ecosystem landing

> **Live site:** [alexar76.github.io/aicom](https://alexar76.github.io/aicom/)

A single-file, dependency-free landing page that explains the whole AICOM
ecosystem (AI-Factory, AIMarket Hub, Protocol, SDKs, desktop apps, contracts)
and links each part to its source and live demo. Sci-fi "Alien Monitor" look
with a live animated galaxy canvas (works on mobile + desktop; degrades to a
calmer drift under `prefers-reduced-motion`).

## Preview locally

```bash
# any static server works — e.g. Node (no deps):
node -e 'import("node:http").then(async({createServer})=>{const{readFile}=await import("node:fs/promises");createServer(async(q,s)=>{let p=q.url==="/"?"/index.html":q.url;try{s.end(await readFile("ecosystem-landing"+p))}catch{s.writeHead(404);s.end()}}).listen(8743,()=>console.log("http://localhost:8743"))})'
```

Or just open `ecosystem-landing/index.html` in a browser.

## Deploy — GitHub Pages (current setup)

[`.github/workflows/pages-ecosystem.yml`](../.github/workflows/pages-ecosystem.yml)
publishes this folder to GitHub Pages on every push to `main` that touches
`ecosystem-landing/**`.

**One-time setup on GitHub:** repo **Settings → Pages → Build and deployment →
Source: GitHub Actions**. After the first run the site is live at
`https://<user>.github.io/<repo>/` (e.g. `https://alexar76.github.io/aicom/`).

### Custom domain (optional, later)

Add a `CNAME` file in this folder containing the bare domain (e.g. `aicom.dev`),
point the domain's DNS at GitHub Pages, then enable HTTPS in Settings → Pages.

## Notes

- Sub-project links point at **standalone satellite repos**
  (`github.com/alexar76/<repo>`); payment contracts remain under
  `github.com/alexar76/aicom/tree/main/contracts`.
- Both primary CTAs (Star on GitHub + Try live demo) appear in the hero and the
  closing section.
- No external JS/CSS except the Google Fonts (Orbitron / Rajdhani) and the
  YouTube thumbnail used for the social preview image. No trackers.
- `.nojekyll` disables Jekyll processing on Pages.
