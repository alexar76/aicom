"""
Shared visual execution standards for Architect and Developer LLM calls.

Injected into the **system** side of prompts (not into user JSON payloads).
User messages stay data-only: Architect `{ user_brief, style_preset }`, Developer `{ user_brief, architecture }`.
"""

from __future__ import annotations

VISUAL_QUALITY_SYSTEM = """=== VISUAL_QUALITY_SYSTEM (mandatory for any browser-facing UI) ===
These rules override “vibes-only” filler. They apply equally to architecture (`ui_experience`) and to shipped HTML/CSS/SVG.

Typography
- Use real, intentional type: pair a **display** face with a **body** face (Google Fonts or self-hosted). Set scale (fluid `clamp()` where appropriate), line-height, and weight steps — never default to Arial/Inter/system-ui stack without a documented design reason.
- Hierarchy: clear H1→body→caption contrast; avoid wall-of-text; respect readable measure (~65ch) for prose blocks.

SVG (quality bar — not decoration spam)
- Ship **meaningful** SVG: structured `<svg viewBox="…">`, semantic groups (`<g>`), reusable `<defs>` / `<symbol>` where it helps. Paths should look **designed** (clean curves, consistent stroke caps/joins), not random blobs, “gold ovals”, meaningless scribbles, or stock “AI slop” shapes.
- Prefer purposeful illustration: hero scenes, diagrams, patterns, dividers, data marks — **not** a single placeholder ellipse as the whole visual idea.
- Optimize: remove redundant nodes; avoid megabyte inline SVG; use CSS for simple fills/strokes where possible.
- Icons: consistent 24px grid or chosen system; stroke width unified.

Motion
- Motion must **support comprehension** (reveal, feedback, state) — not distract. Prefer CSS transitions/keyframes or small SVG/CSS choreography; specify easing and duration (e.g. 160–280ms, `ease-out`), stagger modestly.
- Always respect `prefers-reduced-motion`: provide reduced or static alternatives.
- Ban tacky defaults as the hero concept: infinite spinners, seizure-flash, or “wobbly” gimmicks unless the brand brief explicitly calls for it.

Anti-patterns (reject in design and in code)
- Generic purple→cyan gradients, glassmorphism clones, or “three feature cards + gradient hero” with no brand tie-in.
- Decorative SVG that is only a fuzzy glow + meaningless squiggle.
- Illegible thin grey text on glass; broken contrast vs WCAG-ish targets for body copy.

When `ui_experience` / `style_preset` already defines tokens, typography, and `svg_creative_brief`, **execute them faithfully** in implementation — do not replace with a weaker generic substitute."""

USER_DATA_JSON_MARKER = "### USER_DATA_JSON"
