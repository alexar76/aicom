# AICOM Ecosystem — machine economy atlas

Canonical multilingual ecosystem landing: **[ecosystem.modelmarket.dev](https://ecosystem.modelmarket.dev/)**.

| Site | Purpose |
| --- | --- |
| [ecosystem.modelmarket.dev](https://ecosystem.modelmarket.dev/) | Canonical ecosystem landing: the machine economy and its projects. |
| [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev/) | AICOM factory landing: what the autonomous company builds, how it works, and when it uses subcontractors. |
| [magic-ai-factory.com](https://magic-ai-factory.com/) | The working AICOM factory and its product storefront. |

This directory also provides the source for a future GitHub Pages mirror at [alexar76.github.io](https://alexar76.github.io/).
Generated pages use the ecosystem canonical domain. The current GitHub Pages homepage redirects to the factory landing at `modeldev.modelmarket.dev`; updating the repository README does not change that redirect.
Full GitHub Pages publication is a separate operation.

## Edit and preview

Canonical source: `scripts/github-io/` in [alexar76/aicom](https://github.com/alexar76/aicom).

```sh
python3 build.py
python3 validate.py
python3 -m http.server 3408 --bind 127.0.0.1
```

Open `http://127.0.0.1:3408/` (English), `/ru/`, `/es/`, `/fr/` or `/zh/`.
Edit `content.json` for copy, `build.py` for page structure and project links,
`assets/site.css` for layout, and `assets/site.js` for project filtering.
All five HTML pages are generated and committed, so GitHub Pages needs no build dependencies.
No analytics, third-party font requests, authentication, or backend are required.

`assets/scene.js` and `assets/vendor/` contain a self-hosted Three.js illustration.
It supports continuous rotation, pointer/touch dragging, arrow-key rotation, reduced motion, offscreen suspension, and an HTML/CSS fallback.
The illustration is conceptual, not telemetry. All navigation and content work without WebGL or JavaScript.
Three.js licensing is retained in `assets/vendor/LICENSE`.

## Publishing

Review the generated files before publishing. From the monorepo,
`./scripts/publish_github_io.sh` mirrors this directory to the user-site repository.
An ordinary pull request in this repository is also supported. GitHub Pages serves `main` at `/`;
project Pages such as `/gaia/` are separate repositories and are unaffected.
Do not edit generated HTML without updating `content.json` or `build.py`.
