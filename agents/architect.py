"""
Architect Agent
===============
Responsible for:
- Designing system architecture
- Defining component structure
- Planning data models and APIs
- Technology stack decisions
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from llm import GenerationConfig, LLMRouter
from llm.agent_prompt_split import (
    build_architect_system_prompt,
    build_architect_user_data,
    format_user_data_message,
)
from llm.content_languages import ensure_architecture_content_language
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_ARCHITECTURE_SEC

from .base_agent import AgentInput, AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

from agents.prompts.architect_role import ARCHITECT_SYSTEM_PROMPT


def _needs_ui_experience(arch: dict, spec: dict, landing_charter: bool) -> bool:
    """Browser deliverables need a structured UI brief for the Developer."""
    if landing_charter:
        return True
    if isinstance(spec, dict) and spec.get("delivery_profile") == "marketing_landing":
        return True
    ts = arch.get("tech_stack") if isinstance(arch, dict) else None
    if isinstance(ts, dict):
        fe = str(ts.get("frontend", "")).lower()
        if any(x in fe for x in ("html", "css", "javascript", "react", "vue", "svelte", "spa", "tailwind")):
            return True
    blob = json.dumps(spec, ensure_ascii=False).lower() if isinstance(spec, dict) else ""
    return bool(any(k in blob for k in ("index.html", "landing page", "marketing landing", "dashboard ui", "single page")))


def _ui_experience_substantial(ux: object) -> bool:
    if not isinstance(ux, dict) or not ux:
        return False
    mood = str(ux.get("mood", "")).strip()
    cv = ux.get("css_variables")
    svg_b = str(ux.get("svg_creative_brief", "")).strip()
    if len(mood) < 40:
        return False
    if not isinstance(cv, dict) or len(cv) < 4:
        return False
    return not len(svg_b) < 30


def _default_ui_experience(idea: str) -> dict:
    """Fallback when the model omits ui_experience — **rotates** presets so builds are not visually identical."""
    snippet = (idea or "product")[:120]
    digest = hashlib.sha256((idea or "default").encode("utf-8")).hexdigest()
    idx = int(digest[:12], 16) % 8

    presets: list[dict] = [
        {
            "mood": (
                f"Warm editorial paper for: {snippet}. Magazine calm — cream stock, deep ink type, "
                "one warm rust or terracotta accent; feels human and print-informed, not another dark SaaS shell."
            ),
            "strict_system_ui": True,
            "css_variables": {
                "--bg-deep": "#f5f0e6",
                "--surface": "#fffdf8",
                "--text": "#1c1914",
                "--text-muted": "rgba(28,25,20,0.62)",
                "--accent": "#c45c26",
                "--accent-2": "#2f4f4f",
                "--radius-lg": "6px",
                "--shadow-soft": "0 18px 48px rgba(28,25,20,0.08)",
            },
            "typography": {
                "display_google_font": "Fraunces",
                "body_google_font": "Source Sans 3",
                "notes": "Serif display for headlines; clean sans for UI. Load from Google Fonts.",
            },
            "signature_moment": "Pull-quote band or oversized numerals in accent; subtle paper grain or noise at 2–4% opacity.",
            "anti_patterns": ["Dark-on-dark tech template", "Electric cyan default", "Inter-only stack"],
        },
        {
            "mood": (
                f"Neo-brutalist clarity for: {snippet}. Raw structure — thick borders, honest grid, monospace energy; "
                "high contrast, almost poster-like; still accessible contrast ratios."
            ),
            "strict_system_ui": False,
            "css_variables": {
                "--bg-deep": "#f0f0f0",
                "--surface": "#ffffff",
                "--text": "#0a0a0a",
                "--text-muted": "#404040",
                "--accent": "#ff4d00",
                "--accent-2": "#000000",
                "--radius-lg": "0px",
                "--shadow-soft": "8px 8px 0 #0a0a0a",
            },
            "typography": {
                "display_google_font": "Space Grotesk",
                "body_google_font": "IBM Plex Mono",
                "notes": "Geometric + mono; headlines can be ALL CAPS sparingly for impact.",
            },
            "signature_moment": "Hard-offset shadow cards (no soft blur stack); one huge typographic hero number or word.",
            "anti_patterns": ["Rounded pastel SaaS cards", "Purple gradient blobs", "Feather shadows only"],
        },
        {
            "mood": (
                f"Soft organic / nature-tech for: {snippet}. Sage, forest, cream; calm confidence; rounded shapes "
                "and generous breathing room — wellness or climate-adjacent without cliché stock leaves everywhere."
            ),
            "strict_system_ui": False,
            "css_variables": {
                "--bg-deep": "#eef5ef",
                "--surface": "#f8faf7",
                "--text": "#1e2b24",
                "--text-muted": "rgba(30,43,36,0.65)",
                "--accent": "#3f6f51",
                "--accent-2": "#c8b88a",
                "--radius-lg": "20px",
                "--shadow-soft": "0 20px 50px rgba(31,63,48,0.12)",
            },
            "typography": {
                "display_google_font": "Fraunces",
                "body_google_font": "Nunito Sans",
                "notes": "Soft humanist tone; avoid generic ‘green tech’ clipart look — use abstract shapes.",
            },
            "signature_moment": "Large soft radial wash behind hero + pill CTAs with inset highlight.",
            "anti_patterns": ["Neon cyber default", "Pure white sterile clinic UI unless spec says so"],
        },
        {
            "mood": (
                f"Sunset D2C energy for: {snippet}. Confident consumer brand — coral, amber, plum accents on deep "
                "twilight base; feels campaign-ready, not corporate gray."
            ),
            "strict_system_ui": False,
            "css_variables": {
                "--bg-deep": "#1a1025",
                "--surface": "rgba(255,255,255,0.07)",
                "--text": "#fff5f0",
                "--text-muted": "rgba(255,245,240,0.7)",
                "--accent": "#ff6b4a",
                "--accent-2": "#fbbf24",
                "--radius-lg": "18px",
                "--shadow-soft": "0 28px 90px rgba(0,0,0,0.5)",
            },
            "typography": {
                "display_google_font": "Sora",
                "body_google_font": "Rubik",
                "notes": "Bold geometric display + rounded body; both on Google Fonts.",
            },
            "signature_moment": "Diagonal sunset mesh gradient in hero + glass pricing strip with warm border glow.",
            "anti_patterns": ["Flat Bootstrap blue", "Generic three-column icon row with gray circles"],
        },
        {
            "mood": (
                f"Swiss / editorial minimal for: {snippet}. Mostly white field, black type, **one** signal accent "
                "(red or electric blue) — luxury restraint, big type, strict grid."
            ),
            "strict_system_ui": True,
            "css_variables": {
                "--bg-deep": "#fafafa",
                "--surface": "#ffffff",
                "--text": "#0b0b0b",
                "--text-muted": "#5c5c5c",
                "--accent": "#e11d48",
                "--accent-2": "#0b0b0b",
                "--radius-lg": "4px",
                "--shadow-soft": "0 1px 0 rgba(0,0,0,0.08)",
            },
            "typography": {
                "display_google_font": "Instrument Serif",
                "body_google_font": "Inter",
                "notes": "Serif headlines optional; keep body highly readable; tight tracking on display.",
            },
            "signature_moment": "Massive left-aligned headline + thin rules; accent only on primary CTA and key numbers.",
            "anti_patterns": ["Glassmorphism stacks", "Multi-accent rainbow", "Cyan+magenta AI trope"],
        },
        {
            "mood": (
                f"Luxe night + gold for: {snippet}. Deep charcoal/black with restrained metallic gold/champagne highlights; "
                "jewelry or fintech-adjacent sophistication — not neon gamer."
            ),
            "strict_system_ui": False,
            "css_variables": {
                "--bg-deep": "#0b0b0d",
                "--surface": "rgba(255,255,255,0.05)",
                "--text": "#f5f0e6",
                "--text-muted": "rgba(245,240,230,0.65)",
                "--accent": "#d4af37",
                "--accent-2": "#c9b8a0",
                "--radius-lg": "12px",
                "--shadow-soft": "0 24px 80px rgba(0,0,0,0.55)",
            },
            "typography": {
                "display_google_font": "Cormorant Garamond",
                "body_google_font": "Manrope",
                "notes": "Elegant contrast; gold as accent lines and hover states, not full fills.",
            },
            "signature_moment": "Fine gold hairline frames + subtle film grain; CTA with gold border and dark fill.",
            "anti_patterns": ["Purple-blue gradient slop", "Comic sans energy", "Cyan as primary accent here"],
        },
        {
            "mood": (
                f"Retro phosphor / terminal soul for: {snippet}. Near-black field with **amber or green** phosphor accents "
                "(not cyan); monospace-leaning UI cues; hacker craft without looking like a bootcamp exercise."
            ),
            "strict_system_ui": False,
            "css_variables": {
                "--bg-deep": "#070a07",
                "--surface": "rgba(57,255,20,0.06)",
                "--text": "#e8ffe8",
                "--text-muted": "rgba(200,255,200,0.55)",
                "--accent": "#39ff14",
                "--accent-2": "#ffb000",
                "--radius-lg": "8px",
                "--shadow-soft": "0 0 40px rgba(57,255,20,0.12)",
            },
            "typography": {
                "display_google_font": "Share Tech Mono",
                "body_google_font": "IBM Plex Sans",
                "notes": "Mono for headlines/labels; sans for long copy; scanline or subtle CRT vignette optional.",
            },
            "signature_moment": "CRT scanline overlay at low opacity + glowing keyline on hero panel edges.",
            "anti_patterns": ["Electric cyan + magenta pair", "Inter-only with no personality"],
        },
        {
            "mood": (
                f"Oceanic calm + sand for: {snippet}. Deep navy/teal depths with sand and mist neutrals; "
                "trust and scale — distinct from generic ‘AI blue’ gradients."
            ),
            "strict_system_ui": False,
            "css_variables": {
                "--bg-deep": "#0a1628",
                "--surface": "rgba(255,255,255,0.06)",
                "--text": "#e8f4ff",
                "--text-muted": "rgba(232,244,255,0.68)",
                "--accent": "#38bdf8",
                "--accent-2": "#fcd34d",
                "--radius-lg": "14px",
                "--shadow-soft": "0 26px 70px rgba(2,12,27,0.55)",
            },
            "typography": {
                "display_google_font": "Outfit",
                "body_google_font": "Plus Jakarta Sans",
                "notes": "Rounded geometric; keep motion soft and buoyant.",
            },
            "signature_moment": "Layered wave or blob SVG mask in hero (CSS clip-path OK) + frosted stat tiles.",
            "anti_patterns": ["Identical palette to previous cyan-magenta dark SaaS clone"],
        },
    ]

    svg_briefs = [
        (
            "Hero: full-width inline SVG with feTurbulence paper grain + soft vignette rect; ornamental **vector** "
            "corner brackets framing the headline (paths, no raster). Section dividers as single stroked paths."
        ),
        (
            "Bold SVG grid: repeating vector crosshair pattern in `<defs><pattern>`; hero **outline** illustration of the "
            "product metaphor built from `<path>` + thick stroke; CTA badges as skewed vector rects."
        ),
        (
            "Organic blobs: layered `<path>` amoebas with low-opacity fills behind hero; `<symbol>` leaf-like abstract "
            "shapes reused in feature rows; soft SVG gradient mesh (multiple `<stop>`) for depth — no stock photo URLs."
        ),
        (
            "Sunset: inline SVG radial + linear gradient mesh in hero; vector **flame/wave** abstract mark beside H1; "
            "pricing cards with SVG corner ribbons (`<path>`)."
        ),
        (
            "Swiss precision: minimal SVG **construction lines** (hairline paths) as decorative grid; one large vector "
            "numeral or monogram from paths; accent bar as pure rect + transform — no bitmap."
        ),
        (
            "Luxe: SVG filigree border around hero card (compound paths); subtle gold gradient defined in `<defs>`; "
            "vector sparkle/star accents as `<use>` symbols."
        ),
        (
            "CRT vibe: SVG scanlines as `<pattern>` overlay; phosphor glow via feGaussianBlur on vector panel edges; "
            "ASCII-style icon row drawn with paths (not a webfont icon pack only)."
        ),
        (
            "Ocean: layered wave `<path>`s with different opacities for parallax feel; bubble circles as vector; "
            "optional SVG compass or anchor motif from paths — all ship inline or as `assets/hero-waves.svg`."
        ),
    ]

    base = dict(presets[idx])
    base["svg_creative_brief"] = svg_briefs[idx]
    base["layout"] = {
        "max_width": "min(1120px, 92vw)",
        "hero_layout": "Two-column on desktop (copy + visual), stacked on mobile; hero min-height ~72vh feel.",
        "section_spacing": "clamp(3rem, 8vw, 6rem) vertical rhythm between major sections",
        "grid_notes": "12-column mental model; feature cards in responsive auto-fit grid minmax(260px,1fr).",
    }
    base["motion"] = {
        "page": "Soft fade/slide-up for hero children stagger ~70ms; respect prefers-reduced-motion.",
        "micro_interactions": "Buttons: 180–220ms ease-out; hover lift or border shift — match the mood above.",
        "scroll": "IntersectionObserver once: sections reveal when ~12% visible; timing 200–320ms.",
        "respect_reduced_motion": True,
    }
    base["anti_patterns"] = list(base.get("anti_patterns", [])) + [
        "Browser-default blue underlined links as primary CTA",
        "Wall of unstyled bullet lists",
        "Reusing the exact same font pairing + accent colors as every other product in this factory",
    ]
    return base


def _ensure_ui_experience(arch: dict, spec: dict, landing_charter: bool, idea: str) -> bool:
    """Return True if factory-default ui_experience was applied."""
    if not isinstance(arch, dict):
        return False
    if not _needs_ui_experience(arch, spec, landing_charter):
        return False
    if _ui_experience_substantial(arch.get("ui_experience")):
        return False
    arch["ui_experience"] = _default_ui_experience(idea)
    return True


def _build_design_system(arch: dict) -> dict:
    ux = arch.get("ui_experience") if isinstance(arch, dict) else {}
    if not isinstance(ux, dict):
        ux = {}
    return {
        "version": 1,
        "mood": ux.get("mood", ""),
        "strict_system_ui": bool(ux.get("strict_system_ui", False)),
        "tokens": ux.get("css_variables", {}),
        "typography": ux.get("typography", {}),
        "layout": ux.get("layout", {}),
        "motion": ux.get("motion", {}),
        "signature_moment": ux.get("signature_moment", ""),
        "svg_creative_brief": ux.get("svg_creative_brief", ""),
        "anti_patterns": ux.get("anti_patterns", []),
    }


def _build_design_pipeline(arch: dict) -> dict:
    """
    Mandatory 3-stage design pipeline artifact:
    moodboard -> layout_system -> final_ui.
    """
    ux = arch.get("ui_experience") if isinstance(arch, dict) else {}
    if not isinstance(ux, dict):
        ux = {}
    typography = ux.get("typography") if isinstance(ux.get("typography"), dict) else {}
    motion = ux.get("motion") if isinstance(ux.get("motion"), dict) else {}
    layout = ux.get("layout") if isinstance(ux.get("layout"), dict) else {}
    tokens = ux.get("css_variables") if isinstance(ux.get("css_variables"), dict) else {}
    anti = ux.get("anti_patterns") if isinstance(ux.get("anti_patterns"), list) else []
    return {
        "version": 1,
        "stages": {
            "moodboard": {
                "intent": ux.get("mood", ""),
                "font_direction": {
                    "display_google_font": typography.get("display_google_font"),
                    "body_google_font": typography.get("body_google_font"),
                },
                "signature_moment": ux.get("signature_moment", ""),
                "anti_patterns": anti,
            },
            "layout_system": {
                "grid_notes": layout.get("grid_notes"),
                "hero_layout": layout.get("hero_layout"),
                "section_spacing": layout.get("section_spacing"),
                "max_width": layout.get("max_width"),
            },
            "final_ui": {
                "tokens": tokens,
                "motion": motion,
                "svg_creative_brief": ux.get("svg_creative_brief", ""),
                "strict_system_ui": bool(ux.get("strict_system_ui", False)),
            },
        },
    }


def _design_variants(idea: str, n: int = 3) -> list[dict]:
    variants: list[dict] = []
    for i in range(max(1, n)):
        ux = _default_ui_experience(f"{idea} :: variant-{i}")
        variants.append(
            {
                "variant_id": f"v{i+1}",
                "mood": ux.get("mood", ""),
                "tokens": ux.get("css_variables", {}),
                "signature_moment": ux.get("signature_moment", ""),
                "svg_creative_brief": ux.get("svg_creative_brief", ""),
            }
        )
    return variants


def _rank_design_variants(variants: list[dict], current_ux: dict) -> tuple[list[dict], dict]:
    """Rank variants and select the best candidate."""
    cur_tokens = {}
    if isinstance(current_ux, dict):
        maybe = current_ux.get("css_variables")
        if isinstance(maybe, dict):
            cur_tokens = maybe
    ranked = []
    for v in variants:
        tokens = v.get("tokens") if isinstance(v.get("tokens"), dict) else {}
        score = 0.0
        score += min(1.0, len(tokens) / 8.0) * 0.35
        score += min(1.0, len(str(v.get("svg_creative_brief", ""))) / 180.0) * 0.35
        overlap = len(set(tokens.keys()) & set(cur_tokens.keys()))
        score += (1.0 - min(1.0, overlap / 8.0)) * 0.30
        vv = dict(v)
        vv["score"] = round(score, 3)
        ranked.append(vv)
    ranked.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    selected = ranked[0] if ranked else {}
    return ranked, selected


def _is_generic_ui_brief(ux: dict) -> bool:
    if not isinstance(ux, dict):
        return True
    blob = " ".join(
        [
            str(ux.get("mood", "")),
            str(ux.get("signature_moment", "")),
            str(ux.get("svg_creative_brief", "")),
            " ".join(map(str, ux.get("anti_patterns", []) if isinstance(ux.get("anti_patterns"), list) else [])),
        ]
    ).lower()
    if len(blob.strip()) < 140:
        return True
    generic = ("modern", "clean", "sleek", "innovative", "professional", "user-friendly", "intuitive")
    hits = sum(1 for g in generic if g in blob)
    return hits >= 4


def _ensure_docker_compose_contract_fields(
    arch: dict,
    spec: dict,
    *,
    landing_charter: bool,
) -> None:
    """
    Merge docker-compose expectations into implementation_contract for full_software.
    Marketing / landing-first charters skip compose requirements.
    """
    if landing_charter:
        return
    if not isinstance(spec, dict) or spec.get("delivery_profile") != "full_software":
        return
    ic = arch.get("implementation_contract")
    if not isinstance(ic, dict):
        return

    dp_raw = ic.get("data_plane")
    dp: list[dict[str, Any]] = [x for x in dp_raw if isinstance(x, dict)] if isinstance(dp_raw, list) else []

    def _store_lower(row: dict) -> str:
        return str(row.get("store", "")).lower()

    needs_db_container = False
    outline: list[str] = []
    for row in dp:
        st = _store_lower(row)
        if st in ("postgresql", "postgres", "mysql", "mariadb", "mongodb", "mongo", "redis", "elasticsearch", "elastic"):
            needs_db_container = True
            if "postgres" in st or st == "postgresql":
                outline.append("postgres")
            elif "mysql" in st or "mariadb" in st:
                outline.append("mysql")
            elif "mongo" in st:
                outline.append("mongodb")
            elif "redis" in st:
                outline.append("redis")
            elif "elastic" in st:
                outline.append("elasticsearch")

    rs = ic.get("runnable_services")
    if isinstance(rs, list):
        for svc in rs:
            if not isinstance(svc, dict):
                continue
            n = str(svc.get("name", "")).lower()
            if n in ("api", "backend"):
                outline.append("api")
            elif n in ("web", "frontend", "spa"):
                outline.append("web")
            elif n in ("worker", "notifications"):
                outline.append(n)

    outline = sorted(set(outline))
    if not outline:
        outline = ["api"]

    docker_compose = ic.get("docker_compose")
    if not isinstance(docker_compose, dict):
        docker_compose = {}

    docker_compose.setdefault("required", True)
    docker_compose.setdefault("compose_file", "docker-compose.yml")
    if not docker_compose.get("services_outline"):
        docker_compose["services_outline"] = outline
    prev_db = bool(docker_compose.get("database_in_compose"))
    docker_compose["database_in_compose"] = prev_db or bool(needs_db_container)
    docker_compose.setdefault(
        "host_ports_env_contract",
        "Map host ports with env vars (e.g. API_HOST_PORT, WEB_HOST_PORT, POSTGRES_HOST_PORT when exposing DB) "
        "so `docker compose up` works under parallel factory sandboxes.",
    )

    ic["docker_compose"] = docker_compose

    rl = str(ic.get("repository_layout", "") or "")
    low_rl = rl.lower()
    if "docker-compose" not in low_rl and "compose.yaml" not in low_rl and "compose.yml" not in low_rl:
        ic["repository_layout"] = (rl.rstrip() + "\n  docker-compose.yml # REQUIRED — orchestrates services + DB/cache from data_plane\n").strip()

    fs = ic.get("forbidden_shortcuts")
    if not isinstance(fs, list):
        fs = []
    extras = [
        "Shipping full_software without a root docker-compose.yml (or compose.yaml) that starts runnable_services and satisfies data_plane.",
        "Running PostgreSQL/MySQL/Redis/Elasticsearch as implicit host installs instead of compose services when data_plane lists them.",
        "Hard-coded published ports only — parallel sandboxes and CI cannot bind; use API_HOST_PORT / WEB_HOST_PORT style overrides.",
    ]
    for e in extras:
        if e not in fs:
            fs.append(e)
    ic["forbidden_shortcuts"] = fs
    arch["implementation_contract"] = ic


def _ensure_testing_contract_fields(
    arch: dict,
    spec: dict,
    *,
    landing_charter: bool,
) -> None:
    """
    Enforce test pyramid (component → functional → UI) and sandbox demo login when OLTP DB exists.
    """
    if landing_charter:
        return
    if not isinstance(spec, dict) or spec.get("delivery_profile") != "full_software":
        return
    ic = arch.get("implementation_contract")
    if not isinstance(ic, dict):
        return

    dp_raw = ic.get("data_plane")
    dp: list[dict[str, Any]] = [x for x in dp_raw if isinstance(x, dict)] if isinstance(dp_raw, list) else []

    def _needs_demo_user_seed() -> bool:
        for row in dp:
            st = str(row.get("store", "")).lower()
            if any(k in st for k in ("postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongo")):
                return True
        return False

    tc = ic.get("testing_contract")
    if not isinstance(tc, dict):
        tc = {}

    tc.setdefault("layers_ordered", ["component_unit", "functional_integration", "ui_e2e"])
    tc.setdefault(
        "execution_note",
        "Run tests strictly in order: (1) component/unit in isolation, (2) functional/integration (API + DB, no browser), "
        "(3) UI/e2e last against a running stack.",
    )

    if _needs_demo_user_seed():
        demo = tc.get("sandbox_demo_credentials")
        if not isinstance(demo, dict):
            demo = {}
        demo["required"] = True
        demo.setdefault("seed_email", "sandbox.demo@aicom.local")
        # Match factory `AIFACTORY_SANDBOX_DEMO_PASSWORD` docker-compose default (see demo_credentials.py).
        demo.setdefault("seed_password", "AfSc7xK9mR2nL4vP8qW1jH0fT5dB3cZyEu")
        demo.setdefault(
            "env_var_names",
            "SANDBOX_DEMO_EMAIL, SANDBOX_DEMO_PASSWORD; frontend mirrors VITE_SANDBOX_DEMO_EMAIL, VITE_SANDBOX_DEMO_PASSWORD when using Vite.",
        )
        demo.setdefault(
            "seed_mechanism",
            "Alembic/Flyway/sql seed or startup hook creates this user when compose boots; document in README.",
        )
        demo.setdefault(
            "ui_prefill",
            "Login (and similar) forms must initialize email/password fields from env when SANDBOX_DEMO_* is set — reviewers must not hunt passwords in sandbox.",
        )
        tc["sandbox_demo_credentials"] = demo

    ic["testing_contract"] = tc

    vc = ic.get("verification_commands")
    if not isinstance(vc, list):
        vc = []
    tier_cmds = [
        "cd backend && (pytest tests/unit -q || pytest -q -m unit || python -m pytest tests/unit -q)",
        "cd backend && (pytest tests/integration -q || pytest -q -m integration || python -m pytest tests/integration -q)",
        "cd frontend && (npm run test:e2e --if-present || npx playwright test --pass-with-no-tests || true)",
    ]
    for c in tier_cmds:
        if c not in vc:
            vc.append(c)
    ic["verification_commands"] = vc

    fs = ic.get("forbidden_shortcuts")
    if not isinstance(fs, list):
        fs = []
    for e in (
        "Skipping the test pyramid — UI/e2e before green component/unit and functional/integration suites.",
        "Login-capable app with PostgreSQL/MySQL/MongoDB but no seeded sandbox demo user + env-driven prefilled credentials on forms.",
    ):
        if e not in fs:
            fs.append(e)
    ic["forbidden_shortcuts"] = fs
    arch["implementation_contract"] = ic


def _ensure_implementation_contract(
    arch: dict,
    spec: dict,
    idea: str,
    *,
    landing_charter: bool,
) -> None:
    """
    Guarantee full_software builds carry a concrete repo/runtime contract for the Developer.
    Fills from tech_stack heuristics when the LLM omitted the block.
    """
    if not isinstance(arch, dict):
        return
    if not isinstance(spec, dict) or spec.get("delivery_profile") != "full_software":
        return
    if landing_charter:
        return

    ic = arch.get("implementation_contract")
    if isinstance(ic, dict) and isinstance(ic.get("runnable_services"), list) and len(ic["runnable_services"]) > 0:
        fs = ic.get("forbidden_shortcuts")
        if not isinstance(fs, list) or len(fs) < 1:
            ic = dict(ic)
            ic["forbidden_shortcuts"] = [
                "Shipping only a root index.html without the backend processes listed in runnable_services.",
                "Stack prose (K8s/Elastic/RabbitMQ) without a runnable local path (docker-compose or README) matching data_plane.",
            ]
            arch["implementation_contract"] = ic
        _ensure_docker_compose_contract_fields(arch, spec, landing_charter=landing_charter)
        _ensure_testing_contract_fields(arch, spec, landing_charter=landing_charter)
        return

    ts = arch.get("tech_stack") if isinstance(arch.get("tech_stack"), dict) else {}
    fe = str(ts.get("frontend", "")).lower()
    be = str(ts.get("backend", "")).lower()
    db = str(ts.get("database", "")).lower()

    services: list[dict[str, Any]] = []
    if any(x in be for x in ("fastapi", "python", "django", "flask", "uvicorn")):
        services.append(
            {
                "name": "api",
                "runtime": "python",
                "framework": "FastAPI",
                "entrypoint": "backend/app/main.py",
                "start_command": "cd backend && uvicorn app.main:app --reload --port 8000",
                "port_hint": 8000,
                "health_or_probe": "GET /health or /api/health",
            }
        )
    elif any(x in be for x in ("nestjs", "express", "node")):
        services.append(
            {
                "name": "api",
                "runtime": "nodejs",
                "framework": "NestJS or Express",
                "entrypoint": "backend/src/main.ts",
                "start_command": "cd backend && npm install && npm run start:dev",
                "port_hint": 3000,
                "health_or_probe": "GET /health",
            }
        )
    elif any(x in be for x in ("asp.net", "dotnet", "c#", ".net")):
        services.append(
            {
                "name": "api",
                "runtime": "dotnet",
                "framework": "ASP.NET Core",
                "entrypoint": "backend/Program.cs",
                "start_command": "cd backend && dotnet run",
                "port_hint": 5000,
                "health_or_probe": "GET /health",
            }
        )
    else:
        services.append(
            {
                "name": "api",
                "runtime": "python",
                "framework": "FastAPI",
                "entrypoint": "backend/app/main.py",
                "start_command": "cd backend && uvicorn app.main:app --reload --port 8000",
                "port_hint": 8000,
                "health_or_probe": "GET /health",
            }
        )

    if any(x in fe for x in ("react", "vite", "typescript", "next.js", "spa")):
        services.append(
            {
                "name": "web",
                "runtime": "nodejs",
                "framework": "React + Vite",
                "entrypoint": "frontend/package.json",
                "start_command": "cd frontend && npm install && npm run dev -- --host",
                "port_hint": 5173,
                "health_or_probe": "GET / loads SPA",
            }
        )

    data_plane: list[dict[str, str]] = []
    if "postgres" in db or "postgresql" in db:
        data_plane.append({"store": "postgresql", "role": "OLTP", "env_var_hint": "DATABASE_URL"})
    elif "sqlite" in db:
        data_plane.append({"store": "sqlite", "role": "OLTP", "env_var_hint": "SQLITE_PATH"})
    if "redis" in db:
        data_plane.append({"store": "redis", "role": "cache", "env_var_hint": "REDIS_URL"})
    if not data_plane:
        data_plane.append({"store": "sqlite", "role": "OLTP", "env_var_hint": "SQLITE_PATH"})

    snippet = (idea or "product")[:80]
    layout = (
        "repo-root/\n"
        "  backend/           # Primary API (matches tech_stack.backend)\n"
        "  frontend/          # SPA when React/Vite implied\n"
        "  docker-compose.yml # REQUIRED — api/web + Postgres/Redis/etc. from data_plane (not host-wide installs)\n"
        "  README.md          # docker compose up + per-service dev commands + tests\n"
        f"  # Charter: {snippet}\n"
    )

    dc_services = ["api"]
    if any(x in fe for x in ("react", "vite", "typescript", "next.js", "spa")):
        dc_services.append("web")
    if "postgres" in db or "postgresql" in db:
        dc_services.append("postgres")
    if "redis" in db:
        dc_services.append("redis")

    arch["implementation_contract"] = {
        "repository_layout": layout,
        "runnable_services": services,
        "data_plane": data_plane,
        "docker_compose": {
            "required": True,
            "compose_file": "docker-compose.yml",
            "services_outline": sorted(set(dc_services)),
            "database_in_compose": ("postgres" in db or "postgresql" in db or "redis" in db or "mysql" in db),
            "host_ports_env_contract": (
                "Use API_HOST_PORT and WEB_HOST_PORT (and POSTGRES_HOST_PORT if DB port is published) for host bindings."
            ),
        },
        "integration_surface": (
            "Expose API under /api from backend; frontend dev server proxies or uses VITE_* env — document CORS and URLs in README."
        ),
        "verification_commands": [
            "docker compose config",
            "docker compose up -d --build",
            "cd backend && (pytest tests/unit -q || pytest -q -m unit || python -m pytest tests/unit -q)",
            "cd backend && (pytest tests/integration -q || pytest -q -m integration || python -m pytest tests/integration -q)",
            "cd frontend && (npm run build || true)",
            "cd frontend && (npm run test:e2e --if-present || npx playwright test --pass-with-no-tests || true)",
        ],
        "testing_contract": {
            "layers_ordered": ["component_unit", "functional_integration", "ui_e2e"],
            "execution_note": (
                "Strict order: component/unit tests first, then functional/integration (API+DB), then UI e2e last."
            ),
        },
        "forbidden_shortcuts": [
            "Delivering only static index.html at repo root when runnable_services lists an API server.",
            "Listing Elasticsearch/K8s/RabbitMQ in tech_stack without a minimal runnable substitute or docker-compose service.",
        ],
    }
    logger.info(
        "implementation_contract synthesized from tech_stack for full_software build (Architect fallback)"
    )
    _ensure_docker_compose_contract_fields(arch, spec, landing_charter=landing_charter)
    _ensure_testing_contract_fields(arch, spec, landing_charter=landing_charter)


def _novelty_score_against_recent_ui(ux: dict) -> float:
    """Simple token novelty: 1 - max Jaccard similarity against last 20 UI briefs."""
    if not isinstance(ux, dict):
        return 0.0
    cur_blob = " ".join(
        [str(ux.get("mood", "")), str(ux.get("signature_moment", "")), str(ux.get("svg_creative_brief", ""))]
    ).lower()
    cur_tokens = {t for t in re.split(r"[^a-z0-9]+", cur_blob) if len(t) > 2}
    if not cur_tokens:
        return 0.0
    from core.paths import arch_data_dir

    root = arch_data_dir()
    files = sorted(root.glob("*/architecture.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    max_sim = 0.0
    for p in files:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            arch = raw.get("architecture") if isinstance(raw, dict) else raw
            u = arch.get("ui_experience") if isinstance(arch, dict) else {}
            if not isinstance(u, dict):
                continue
            blob = " ".join([str(u.get("mood", "")), str(u.get("signature_moment", "")), str(u.get("svg_creative_brief", ""))]).lower()
            tokens = {t for t in re.split(r"[^a-z0-9]+", blob) if len(t) > 2}
            if not tokens:
                continue
            inter = len(cur_tokens & tokens)
            union = len(cur_tokens | tokens)
            sim = (inter / union) if union else 0.0
            max_sim = max(max_sim, sim)
        except Exception:
            continue
    return max(0.0, 1.0 - max_sim)


class ArchitectAgent(BaseAgent):
    """Architect Agent - designs system architecture from specifications."""

    def __init__(self, llm_router: LLMRouter):
        super().__init__(
            agent_type="architect",
            llm_router=llm_router,
            task_type="architecture_design",
        )

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        start_time = time.time()
        product_id = agent_input.product_id
        spec = agent_input.data.get("specification", {})
        idea = agent_input.data.get("idea", "")
        production_mode = bool(agent_input.data.get("production_mode"))
        peer_feedback = agent_input.data.get("peer_review_feedback")

        self._log("INFO", f"Designing architecture for {product_id}")

        try:
            spec_str = json.dumps(spec, indent=2) if spec else idea
            admin_raw = (agent_input.data.get("admin_instructions") or "").strip()
            admin_l = admin_raw.lower()
            blob_l = spec_str.lower()

            research_context = ""
            research_path = self.data_root / "state" / product_id / "market_research.json"
            if research_path.is_file():
                try:
                    raw_mr = json.loads(research_path.read_text(encoding="utf-8"))
                    research_context = json.dumps(raw_mr, indent=2, ensure_ascii=False)
                    if len(research_context) > 28_000:
                        research_context = research_context[:28_000] + "\n…[truncated]"
                    self._log("INFO", "Architect loaded market_research.json for context")
                except (json.JSONDecodeError, OSError) as e:
                    self._log("WARNING", f"Architect could not read market research: {e}")
            landing_charter = any(
                k in admin_l or k in blob_l
                for k in (
                    "marketing landing",
                    "landing page",
                    "single scroll",
                    "promo page",
                    "html/css/js",
                    "single-page",
                    "promotional",
                )
            )

            landing_note = ""
            if landing_charter:
                landing_note = (
                    "\nThis build is **landing-first**. Prefer static files only; align components with the Product Idea phrase.\n"
                )

            full_sw = isinstance(spec, dict) and spec.get("delivery_profile") == "full_software"
            full_note = ""
            if full_sw and not landing_charter:
                full_note = (
                    "\nThis build is **full_software**: design **runnable** services — persistence models, API contracts, "
                    "auth/session boundaries, and deployment topology — exactly as demanded by functional_requirements. "
                    "You MUST emit a complete **implementation_contract** JSON object (repository_layout, runnable_services, "
                    "data_plane, docker_compose, testing_contract, verification_commands, forbidden_shortcuts). Root **docker-compose.yml** must "
                    "orchestrate every service in data_plane (Postgres/Redis in containers, not mystery host daemons) except "
                    "file-only SQLite when explicit. **testing_contract** must mandate component/unit → functional/integration → UI/e2e "
                    "in that order; if Postgres/MySQL/Mongo appear in data_plane, include **sandbox_demo_credentials** with seeded "
                    "user + env-driven prefilled login forms.\n"
                    "The Developer will ship Python/Node/.NET/React files accordingly — not a "
                    "single marketing HTML file pretending to be the whole product.\n"
                    "Market research (when attached below) should inform integration posture and differentiation surfaces.\n"
                )

            ux_note = ""
            if landing_charter or (isinstance(spec, dict) and spec.get("delivery_profile") == "marketing_landing"):
                ux_note = (
                    "\nInclude a **rich `ui_experience` object** (designer-quality: tokens, typography, motion, "
                    "signature_moment). The Developer will implement it literally alongside HTML/CSS.\n"
                )
            elif full_sw and not landing_charter:
                ux_note = (
                    "\nInclude a **rich, distinctive `ui_experience` object** for the shipped browser UI (same fields as "
                    "landing mode). **Visual diversity:** pick a bold art direction that fits THIS product — not the "
                    "same dark+cyan+glass formula as every other build; the Developer binds to these tokens.\n"
                )

            methodology_block = ""
            meth_path = self.data_root / "state" / product_id / "methodology_spec_review.json"
            if meth_path.is_file():
                try:
                    mr = json.loads(meth_path.read_text(encoding="utf-8"))
                    blob = json.dumps(mr, ensure_ascii=False, indent=2)
                    if len(blob) > 28_000:
                        blob = blob[:28_000] + "\n…[truncated]"
                    methodology_block = (
                        "\n=== DOMAIN METHODOLOGY REVIEW (pre-architecture; treat as TZ backlog) ===\n"
                        "Resolve `findings` in components, data_models, api_endpoints, and acceptance-oriented notes. "
                        "If `passed` is false, architecture must close the gaps (entities, capabilities, lifecycle) "
                        "without shrinking agreed scope.\n"
                        f"{blob}\n"
                    )
                    self._log("INFO", "Architect loaded methodology_spec_review.json for remediation backlog")
                except (json.JSONDecodeError, OSError) as e:
                    self._log("WARNING", f"Architect could not read methodology review: {e}")

            interface_locale = agent_input.data.get("interface_locale")
            product_content_locale = agent_input.data.get("content_locale")

            prompt = format_user_data_message(
                build_architect_user_data(
                    idea=idea,
                    spec=spec if isinstance(spec, dict) else {},
                    admin_instructions=admin_raw,
                    landing_charter=landing_charter,
                    peer_feedback=peer_feedback,
                    research_context=research_context,
                    methodology_block=methodology_block,
                    landing_note=landing_note,
                    full_note=full_note,
                    ux_note=ux_note,
                    interface_locale=str(interface_locale) if interface_locale else None,
                    content_locale=str(product_content_locale) if product_content_locale else None,
                )
            )
            system_prompt = build_architect_system_prompt(ARCHITECT_SYSTEM_PROMPT)

            config = GenerationConfig(
                temperature=0.7,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_ARCHITECTURE_SEC,
                json_mode=True,  # openai_compatible skips response_format for reasoning models
            )

            response = await self._generate(
                prompt,
                config=config,
                agent_input=agent_input,
                system_prompt=system_prompt,
            )

            arch = self._extract_json(response)
            if arch is None:
                elapsed = time.time() - start_time
                self._log("WARNING", f"Architecture generation failed: LLM returned non-JSON response for {product_id}")
                return AgentOutput(
                    task_id=agent_input.task_id,
                    product_id=product_id,
                    agent_type=self.agent_type,
                    success=False,
                    error="LLM returned invalid/non-JSON response — architecture generation failed",
                    timestamp=time.time(),
                    metrics={"elapsed_seconds": elapsed},
                )

            _ensure_implementation_contract(
                arch,
                spec if isinstance(spec, dict) else {},
                idea,
                landing_charter=landing_charter,
            )

            brief_for_lang = "\n".join(
                p
                for p in (
                    str(idea or ""),
                    admin_raw,
                    json.dumps(spec, ensure_ascii=False) if isinstance(spec, dict) else "",
                )
                if p
            )
            lang_code = ensure_architecture_content_language(
                arch,
                product_content_locale=product_content_locale,
                interface_locale=interface_locale,
                user_text=brief_for_lang,
            )
            self._log("INFO", f"content_language={lang_code} for {product_id}")

            if _ensure_ui_experience(arch, spec if isinstance(spec, dict) else {}, landing_charter, idea):
                self._log("INFO", "ui_experience was missing or shallow — applied factory default for browser UI")
            design_system = _build_design_system(arch)
            design_pipeline = _build_design_pipeline(arch)
            design_variants = _design_variants(idea, 3)
            ranked_variants, selected_variant = _rank_design_variants(
                design_variants,
                arch.get("ui_experience") if isinstance(arch, dict) else {},
            )
            novelty = _novelty_score_against_recent_ui(arch.get("ui_experience") if isinstance(arch, dict) else {})
            if production_mode:
                ux = arch.get("ui_experience") if isinstance(arch, dict) else {}
                if _is_generic_ui_brief(ux):
                    raise RuntimeError("production_mode: architecture ui_experience is too generic")
                if novelty < 0.18:
                    raise RuntimeError(
                        f"production_mode: novelty score too low ({novelty:.2f}) vs recent architecture outputs"
                    )

            self._save_artifact(product_id, "arch", {
                "product_id": product_id,
                "architecture": arch,
                "design_system": design_system,
                "novelty_score": round(novelty, 3),
                "created_at": time.time(),
                "agent": "architect",
            }, "architecture.json")
            self._save_artifact(
                product_id,
                "arch",
                {
                    "product_id": product_id,
                    "design_system": design_system,
                    "design_pipeline": design_pipeline,
                    "created_at": time.time(),
                    "agent": "architect",
                },
                "design_system.json",
            )
            self._save_artifact(
                product_id,
                "arch",
                {
                    "product_id": product_id,
                    "design_pipeline": design_pipeline,
                    "design_variants": ranked_variants,
                    "selected_variant": selected_variant,
                    "created_at": time.time(),
                    "agent": "architect",
                },
                "design_pipeline.json",
            )

            elapsed = time.time() - start_time
            self._log("INFO", f"Architecture design complete ({elapsed:.1f}s)")

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=True,
                data={
                    "architecture": arch,
                    "design_system": design_system,
                    "design_pipeline": design_pipeline,
                    "design_variants": ranked_variants,
                    "selected_variant": selected_variant,
                    "novelty_score": round(novelty, 3),
                    "arch_file": f"arch/{product_id}/architecture.json",
                    "peer_review": {
                        "recommended": "approve",
                        "blockers": [],
                        "notes": "Architecture/design pipeline prepared for implementation.",
                    },
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )

        except Exception as e:
            elapsed = time.time() - start_time
            self._log("ERROR", f"Architecture design failed: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=product_id,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
