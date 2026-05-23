"""
Delivery mode inference and validation for DeveloperAgent.
Admin instructions override default web-stack behavior.
"""
from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any


class DeliveryMode(str, Enum):
    WEB_APP = "web_app"
    PYTHON_CLI = "python_cli"
    DESKTOP_APP = "desktop_app"


def _spec_delivery_profile(specification: dict[str, Any] | None) -> str | None:
    if not isinstance(specification, dict):
        return None
    raw = specification.get("delivery_profile")
    return str(raw).strip() if raw else None


def infer_desktop_stack(admin_instructions: str | None, specification: dict[str, Any] | None) -> str:
    """Return ``tauri``, ``flutter``, or ``electron`` (default tauri)."""
    blob = f"{admin_instructions or ''}\n{json.dumps(specification or {})}".lower()
    if "flutter" in blob:
        return "flutter"
    if "electron" in blob:
        return "electron"
    return "tauri"


def infer_delivery_mode(
    admin_instructions: str | None,
    specification: dict[str, Any] | None,
    delivery_profile: str | None = None,
) -> DeliveryMode:
    """
    Decide whether output must be browser web assets, Python CLI/package, or desktop app.

    Default remains WEB_APP for backward compatibility when unconstrained.
    """
    from core.delivery_profile import DESKTOP_APP, normalize_delivery_profile

    dp_raw = delivery_profile or _spec_delivery_profile(specification)
    if dp_raw and normalize_delivery_profile(dp_raw) == DESKTOP_APP:
        return DeliveryMode.DESKTOP_APP

    a = (admin_instructions or "").strip().lower()
    spec = specification or {}
    spec_text = json.dumps(spec).lower()

    # Explicit browser / SPA requests
    web_hints = (
        "browser only",
        "single page app",
        "react ",
        "vue ",
        "next.js",
        "svelte",
        "landing page",
        "dashboard ui",
        "must use html",
    )
    if any(h in a for h in web_hints):
        return DeliveryMode.WEB_APP

    desktop_hints = (
        "desktop app",
        "tauri",
        "electron",
        "flutter desktop",
        "native client",
        "system tray",
        "installable",
        "macos app",
        "windows app",
    )
    if any(h in a for h in desktop_hints):
        return DeliveryMode.DESKTOP_APP
    if any(
        phrase in spec_text
        for phrase in (
            "desktop app",
            "tauri",
            "electron",
            "flutter desktop",
            "native client",
            "system tray",
        )
    ):
        return DeliveryMode.DESKTOP_APP

    # Strong Python CLI signals (admin wins over vague defaults)
    py_kw = bool(re.search(r"\bpython\b", a)) or "python" in spec_text
    cli_kw = bool(
        re.search(r"\b(cli|command[\s-]?line|terminal)\b", a)
        or re.search(r"\b(typer|click|argparse)\b", a)
        or "command line" in spec_text
        or "cli tool" in spec_text
    )
    if py_kw and cli_kw:
        return DeliveryMode.PYTHON_CLI

    if "python only" in a and cli_kw:
        return DeliveryMode.PYTHON_CLI

    # Reject web stack explicitly
    if py_kw and any(
        x in a for x in ("no html", "no browser", "not a website", "without html", "no javascript")
    ):
        return DeliveryMode.PYTHON_CLI

    # Specification describes a marketing landing → browser stack (after explicit CLI signals above)
    if any(
        phrase in spec_text
        for phrase in (
            "marketing landing",
            "landing page",
            "promotional landing",
            "promo page",
            "single scroll",
            "single-page marketing",
            "hero section",
            "sales page",
        )
    ):
        return DeliveryMode.WEB_APP

    # CLI tooling implied without the word "python" (this factory defaults to Python)
    web_forbid = any(w in a for w in ("html", "browser", "react", "vue", "javascript", "spa ", "css "))
    if re.search(r"\b(cli|command[\s-]?line)\b", a) and not web_forbid:
        if any(w in a for w in ("python", "pip ", "pypi", "typer", "click", "argparse")):
            return DeliveryMode.PYTHON_CLI
        if re.search(r"\b(todo|utility|tool|installer|scanner)\b", a):
            return DeliveryMode.PYTHON_CLI

    return DeliveryMode.WEB_APP


def system_prompt_for_mode(mode: DeliveryMode, *, desktop_stack: str = "tauri") -> str:
    """Stack-specific rules appended into the developer system prompt."""
    if mode == DeliveryMode.PYTHON_CLI:
        return """=== REQUIRED OUTPUT STACK: PYTHON CLI (NOT A WEBSITE) ===
- Deliver ONLY a Python 3 project: .py files, optional pyproject.toml / requirements.txt / README.md / tests/test_*.py.
- Entry point: main.py OR src/__main__.py OR cli.py using argparse, Typer, or Click.
- Implement the product as a command-line tool users run with `python ...` — NOT as HTML/JS/CSS pages.
- FORBIDDEN in deliverables: .html, .htm, .jsx, .tsx, .vue, .css (unless trivial stub — prefer NONE), .js (except no JS at all for CLI).
- Do NOT create index.html, app.js, or SPA assets under any circumstance for this mode.
- Include README with install/run examples (e.g. pip install -e . ; python -m mycli --help).
"""

    if mode == DeliveryMode.DESKTOP_APP:
        stack = (desktop_stack or "tauri").strip().lower()
        if stack == "flutter":
            return """=== REQUIRED OUTPUT STACK: FLUTTER DESKTOP (NOT A WEBSITE) ===
- Deliver a **Flutter desktop** project for macOS / Windows / Linux.
- Required: pubspec.yaml, lib/main.dart, README.md with `flutter pub get` + `flutter run -d macos|windows|linux`.
- Include at least one polished screen implementing the product charter (Material 3 or custom theme).
- Optional: integration_test/ or test/widget_test.dart with a smoke test.
- FORBIDDEN as primary deliverable: standalone marketing index.html without Flutter project structure.
- Ship code_manifest.json listing all source files. No placeholder "coming soon" UI.
"""
        if stack == "electron":
            return """=== REQUIRED OUTPUT STACK: ELECTRON DESKTOP ===
- Deliver an Electron app: package.json (with electron dependency), main process entry (main.js or electron/main.ts), preload if needed.
- Required UI folder (renderer/) with index.html + CSS + JS implementing the product workflow.
- README.md with `npm install` + `npm start` and notes for `npm run build` / electron-builder when applicable.
- FORBIDDEN: server-only backend without a desktop shell window.
"""
        return """=== REQUIRED OUTPUT STACK: TAURI v2 DESKTOP (NOT A BROWSER-ONLY SITE) ===
- Deliver a **Tauri v2** desktop app scaffold (reference: packaging/templates/tauri_desktop/).
- Required tree:
  - src-tauri/Cargo.toml, src-tauri/tauri.conf.json, src-tauri/src/main.rs (or lib.rs + main.rs)
  - ui/index.html + ui/style.css + ui/app.js (WebView UI implementing the product charter)
  - README.md with prerequisites (Rust, Node) and commands: `cd src-tauri && cargo tauri dev` / `cargo tauri build`
- Register Tauri commands for core product actions (local file I/O, settings, marketplace hooks as stubs if needed).
- Privacy-first: sensitive user data stays local unless spec explicitly requires sync.
- FORBIDDEN as sole deliverable: a static landing page without Tauri shell.
- Ship code_manifest.json. UI must feel like a real desktop tool (sidebar or toolbar, not a brochure scroll).
"""

    return """=== REQUIRED OUTPUT STACK: WEB (browser) ===
- Deliver a self-contained web UI: at minimum index.html plus CSS/JS as needed.
- No backend server required unless architecture explicitly demands it; vanilla HTML/CSS/JS preferred.
- Entry point MUST include index.html at project root or clearly documented path.

=== WHAT A PROMO LANDING IS (read this) ===
A **promotional landing** = one long scroll that **sells one offer** with emotion and clarity: hero → reasons to believe → benefits/outcomes → proof or urgency (if honest) → **primary CTA repeated**. It must feel like a **real ad campaign page** (Stripe-level polish, D2C brand energy), NOT a homework HTML sheet, NOT a bare form, NOT a documentation wiki.

=== MUST SHIP (check every box before you finish) ===
1. **Hero**: one strong H1 (short), supportive subline, **one obvious primary button** (not a plain blue browser-default link). The primary CTA `<a>` **must not** use `href="#"` or an empty href — use `mailto:…`, `tel:…`, `https://…`, or `href="#section-id"` where that section exists on the same page (real `id="…"`).
2. **Same-page menu / anchors (critical):** Sticky or top `<nav>` links that jump to sections MUST use **hash-only** URLs on this document, e.g. `<a href="#pricing">` with a matching `<section id="pricing">` (or any element `id="pricing"`) in the **same** `index.html`. Do **not** point internal section jumps at another `.html` file, `/…` paths, or full `https://…` URLs — those reload the sandbox iframe instead of scrolling. Every `href="#…"` in the nav must have a visible target `id` on the page.
3. **At least two** styled sections below the hero (e.g. features/benefits grid, “how it works”, testimonials strip, pricing teaser, FAQ accordion — pick what fits the product).
4. **Typography**: load **two named families** from Google Fonts (display + body) via `<link rel="preconnect">` + stylesheet — never deliver Arial/Times-only unless the spec explicitly demands it.
5. **CSS variables** in `:root` for background, surface, text, accent, radius, shadow — then use them everywhere (no scattered magic hex except rare one-offs).
6. **Visual depth**: at least one of — layered gradient background, soft glass card (`backdrop-filter`), subtle mesh/blur, or refined dual shadow on cards. Flat `#cccccc` boxes filling the screen are **not** acceptable as the whole design.
7. **Motion**: transitions on buttons/links/cards (150–300ms); at least one tasteful `@keyframes` OR scroll reveal via small vanilla JS (`IntersectionObserver`). Honor `prefers-reduced-motion`.
8. **Responsive**: flex/grid, fluid type with `clamp()`, readable line length, comfortable tap targets on mobile.

=== SVG & VECTOR — USE THE FULL TOOLKIT (creativity on) ===
You can generate **arbitrary SVG** (inline in HTML and/or dedicated `.svg` files). Treat SVG as a first-class art medium — not only 16px icons.
- **Go deep:** `<defs>` gradients and meshes, `<pattern>` fills, `<mask>`, `<clipPath>`, compound `<path>` illustrations, `<filter>` (blur, turbulence, displacement), `<symbol>` + `<use>`, stroke-based drawings, layered shapes for faux-3D, decorative borders, map/chart primitives, organic blobs, ornamental dividers, animated strokes (SVG/SMIL or CSS where appropriate; honor `prefers-reduced-motion`).
- **Backgrounds & “imagery”:** hero and section backdrops can be **pure SVG** (full-bleed patterns, illustrated scenes, abstract “photo energy” built from vectors). Prefer vector-first so the sandbox never depends on broken stock URLs. Optional small **inline base64** raster only when the brief truly needs bitmap texture — keep total payload sane.
- **Minimum bar:** ship **at least one substantial** custom SVG block or file (dozens of meaningful elements or a full-bleed decorative layer) aligned with `architecture.ui_experience.svg_creative_brief` when present; if absent, still invent equivalent vector hero/section art that fits the mood.

=== ART DIRECTION — ANTI-CLONE (critical) ===
- **Obey `architecture.ui_experience` first** (mood, `css_variables`, typography, `signature_moment`, **`svg_creative_brief`**, `anti_patterns`). That object is the art director’s brief — implement it literally in CSS **and** SVG, not as decoration text only.
- **Do not default** every product to the same “dark void + electric cyan/violet + glass cards + Syne/DM Sans” formula. If the architecture is silent on palette, still pick a **bold, ownable** direction that differs from generic AI-SaaS clones: warm paper editorial, brutalist grid, Swiss minimal, luxe gold-on-black, retro phosphor, oceanic twilight, sunset D2C, organic sage, etc. Commit to **one** coherent pole per product (do not stack every trend).
- Treat consecutive factory builds as a **portfolio**, not duplicates: vary headline scale, section rhythm, and decorative language so this page would not be mistaken for the last one.

=== FORBIDDEN — reads as cheap / “AI slop” ===
- Whole page = centered column of unstyled `<ul>` and paragraphs with browser defaults.
- Times New Roman, default blue underlined links as the only “design”.
- White page + thin gray border boxes everywhere, no shadow, no gradient, no personality.
- Buttons that look like raw `<input type="submit">` with zero CSS.
- Blocks of “Lorem ipsum” as visible filler **without** treating them as design/layout placeholders inside a real grid.
- Broken image URLs; prefer inline SVG, emoji used sparingly, or CSS-only visuals.

=== WEAK MODEL / DEEPSEEK DISCIPLINE ===
Do **not** stop at the first boring layout — but also **do not** converge on the same “dark + cyan glass” safe default every time. If `ui_experience` demands restraint (Swiss / editorial), honor it; if it demands punch, go loud within that brief. One **memorable** visual hook aligned with the chosen art direction is required. Follow the numbered checklist **literally**.

=== QA NOTE ===
Minimalism is allowed only if it is **intentional luxury minimal** (spacing, type scale, one accent), not “unfinished”.
"""


def validate_saved_files(mode: DeliveryMode, relative_paths: list[str]) -> tuple[bool, str]:
    """
    Verify on-disk output matches the mandated delivery mode.

    Returns (ok, error_message).
    """
    rel = [p.replace("\\", "/").strip() for p in relative_paths if p.strip()]
    lower = [x.lower() for x in rel]

    if mode == DeliveryMode.PYTHON_CLI:
        py_ok = any(x.endswith(".py") for x in lower)
        if not py_ok:
            return False, "Python CLI mode requires at least one .py source file"

        banned_suffixes = (".html", ".htm", ".jsx", ".tsx", ".vue")
        bad = [rel[i] for i, p in enumerate(lower) if p.endswith(banned_suffixes)]
        if bad:
            return False, f"Python CLI mode forbids web markup files; remove: {bad}"

        js_bad = [rel[i] for i, p in enumerate(lower) if p.endswith(".js")]
        if js_bad:
            return False, f"Python CLI mode forbids JavaScript deliverables; remove: {js_bad}"

        css_bad = [rel[i] for i, p in enumerate(lower) if p.endswith(".css")]
        if css_bad:
            return False, f"Python CLI mode forbids CSS assets; remove: {css_bad}"

        return True, ""

    if mode == DeliveryMode.DESKTOP_APP:
        norm = [p.replace("\\", "/") for p in lower]
        if any(p.endswith("src-tauri/cargo.toml") for p in norm):
            if not any(p.endswith((".html", ".htm")) for p in norm):
                return False, "Tauri desktop requires HTML UI (ui/index.html or src/index.html)"
            return True, ""
        if any(p.endswith("pubspec.yaml") for p in norm) and any(p.endswith("lib/main.dart") for p in norm):
            return True, ""
        if any(p.endswith("package.json") for p in norm) and any(p.endswith((".html", ".htm")) for p in norm):
            return True, ""
        return False, (
            "Desktop mode requires Tauri (src-tauri/Cargo.toml + HTML UI), "
            "Flutter (pubspec.yaml + lib/main.dart), or Electron (package.json + HTML UI)"
        )

    # WEB_APP
    has_html = any(p.endswith((".html", ".htm")) for p in lower)
    if not has_html:
        return False, "Web stack requires at least one .html file (e.g. index.html)"

    return True, ""


def desktop_app_appendix(desktop_stack: str = "tauri") -> str:
    """Extra charter when delivery_profile is desktop_app."""
    stack = (desktop_stack or "tauri").strip().lower()
    return f"""
=== DESKTOP APP — MARKETPLACE SKU ===
- Category: desktop. Product kind: desktop_app. Framework target: {stack}.
- Ship BUILD.md or README section: install deps, dev run, release build per OS.
- Optional: DESKTOP_PLATFORMS.md listing macOS (.dmg), Windows (.msi/.exe), Linux (.AppImage/.deb).
- Hub lists capability {{slug}}.desktop@v1 — source archive is the full repo under code/.
- Do not depend on cloud-only preview; reviewers run `cargo tauri dev` or `flutter run -d macos`.
"""


def full_software_browser_appendix() -> str:
    """Extra charter when delivery_profile is full_software and stack is web."""
    return """
=== FULL SOFTWARE (WEB) — POLYGLOT MONOREPO + COMPOSE ===
Ship a **runnable mini-product repository**, not a single root index.html when architecture.implementation_contract lists
separate API + SPA services.

Layout: backend/ for the primary API (FastAPI, Nest/Express, ASP.NET Core per Architect); frontend/ for React+Vite when applicable.

**Docker Compose (mandatory for non-landing full_software):** root `docker-compose.yml` starts **all** services implied by
implementation_contract — API, web, and any Postgres/MySQL/Redis/Elasticsearch from **data_plane**. Do not rely on the reviewer
having databases installed on the host. File-only SQLite may live on a mounted volume without a DB container when Architect allows.

**Ports for sandbox/CI:** bind published ports with environment variables, e.g. `${API_HOST_PORT:-8000}:8000`,
`${WEB_HOST_PORT:-5173}:5173`, `${POSTGRES_HOST_PORT:-55432}:5432` when the DB port is exposed for debugging.

Root README.md: `docker compose up -d --build`, health checks, and per-service dev commands from **verification_commands**.

Quality: coherent modules; distinctive interaction aligned with core_features.

**Tests (full_software binding):** implement **implementation_contract.testing_contract** — run **component/unit** tests first, then **functional/integration** (HTTP + database, without relying on browser automation), then **UI/e2e** (Playwright/Cypress) last. Mirror commands in README from **verification_commands** in that order.

**Sandbox + DB:** when **sandbox_demo_credentials** applies, seed the demo user on startup, wire env `SANDBOX_DEMO_EMAIL` / `SANDBOX_DEMO_PASSWORD`, and **prefill** email/password fields on auth forms when those env vars are set (factory iframe preview).

**Demo usability:** ship **migration apply** on compose up (or documented `make migrate`); optional **POST /api/demo/seed** (dev-only) to insert chart/task fixtures so operators never see an empty dashboard after first boot.

**API surface:** FastAPI must expose **OpenAPI** (`/openapi.json`); add **docs/openapi.json** for reviewers.

Honesty: do not claim Elasticsearch/K8s/Celery as live infra without a compose service or documented stub.

Visual identity: follow architecture.ui_experience (tokens, fonts, signature_moment, svg_creative_brief).
"""
