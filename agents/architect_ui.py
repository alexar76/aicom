"""Architect UI experience helpers — presets, design pipeline, novelty.

Split out of ``architect.py`` to keep the agent class readable.
"""
from __future__ import annotations

import hashlib
import json
import re


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

