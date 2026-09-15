#!/usr/bin/env python3
"""
Generate optional neural UI reference templates (vanilla HTML/CSS/JS shells) for the factory pool.

Reads style directions from ``reference_templates/style_presets.json`` and writes one folder per id
under ``AIFACTORY_REFERENCE_TEMPLATES_DIR`` (default: ``<data-root>/reference_templates``).

Requires a configured LLM provider (same as pipeline). Does not run automatically — invoke manually
or from CI when you want to refresh the pool.

Examples:
  AIFACTORY_DATA_ROOT=./data python scripts/generate_reference_templates.py --dry-run
  python scripts/generate_reference_templates.py --only aurora-glass --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("gen-ref-templates")

GENERATOR_PROMPT_HEADER = """You are building a REFERENCE UI SHELL for an AI software factory.
This is not a client project — it is a pattern library the Developer Agent will imitate.

OUTPUT: a single JSON object ONLY (no markdown outside JSON) with shape:
{"files":[{"path":"index.html","content":"...","language":"html"},{"path":"style.css",...},{"path":"app.js",...}]}

Stack: vanilla static site — index.html + style.css + app.js at project root (relative ./ links).

MUST INCLUDE (production-quality patterns):
- CSS variables in :root for colors, radius, shadow, typography; dark mode via class on html or data-theme + prefers-color-scheme.
- Responsive layout: mobile nav (hamburger) with aria-expanded; comfortable tap targets.
- States: loading skeleton block, empty state section, error/alert toast or banner (can be toggled in demo).
- Form with labels, validation messages, aria-invalid / role="alert" where appropriate.
- Motion: tasteful transitions; at least one @keyframes OR scroll reveal; honor prefers-reduced-motion.
- SVG: one substantial decorative or hero SVG (gradients, patterns, or illustration) matching the art direction.
- Use Google Fonts via link if needed (two families max).

FORBIDDEN: lorem as only visible content (placeholder copy ok inside clearly demo-only blocks); broken href="#"; external image hotlinks.

ART DIRECTION (execute fully — this defines style, effects, animation personality):
"""


def _load_presets(repo_root: Path) -> list[dict]:
    p = repo_root / "reference_templates" / "style_presets.json"
    if not p.is_file():
        logger.error("Missing %s", p)
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


async def _generate_one(
    *,
    router,
    preset: dict,
    out_root: Path,
    force: bool,
    dry_run: bool,
) -> dict | None:
    pid = str(preset.get("id") or "").strip()
    title = str(preset.get("title") or pid)
    neural = str(preset.get("neural_prompt") or "").strip()
    if not pid or not neural:
        logger.warning("Skipping invalid preset: %s", preset)
        return None

    dest = out_root / pid
    index_html = dest / "index.html"
    if index_html.is_file() and not force:
        logger.info("[%s] skip (exists, use --force)", pid)
        return {"id": pid, "title": title, "path": pid, "skipped": True}

    if dry_run:
        logger.info("[dry-run] would generate %s — %s", pid, title)
        return {"id": pid, "title": title, "path": pid, "dry_run": True}

    from agents.base_agent import BaseAgent
    from llm import GenerationConfig
    from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_CODE_GENERATION_SEC

    prompt = f"""{GENERATOR_PROMPT_HEADER}
{neural}

Title hint for the shell demo page: {title}

Return JSON with files[] only. Include index.html, style.css, and app.js."""

    config = GenerationConfig(
        temperature=0.72,
        max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
        timeout_sec=min(FACTORY_TIMEOUT_CODE_GENERATION_SEC, 420.0),
        json_mode=True,
        task_type="code_generation",
    )

    logger.info("Generating template %s …", pid)
    raw_text = await router.generate(prompt, task_type="code_generation", config=config)
    data = BaseAgent._extract_json(raw_text)
    if not isinstance(data, dict):
        logger.error("[%s] invalid JSON from model", pid)
        return None

    files = data.get("files")
    if not isinstance(files, list) or not files:
        logger.error("[%s] missing files[] in response", pid)
        return None

    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for fi in files:
        if not isinstance(fi, dict):
            continue
        rel = str(fi.get("path") or "").strip().replace("\\", "/")
        content = fi.get("content")
        if not rel or not isinstance(content, str):
            continue
        # prevent path escape
        if rel.startswith("/") or ".." in rel.split("/"):
            logger.warning("[%s] skip unsafe path %s", pid, rel)
            continue
        fp = dest / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        written.append(rel)

    if not written:
        logger.error("[%s] no files written", pid)
        return None

    logger.info("[%s] wrote %s", pid, ", ".join(written))
    return {"id": pid, "title": title, "path": pid, "files": written}


async def _async_main(args: argparse.Namespace) -> int:
    os.environ.setdefault("AIFACTORY_DATA_ROOT", str(Path(args.data_root).resolve()))

    from web.backend.services.reference_templates import style_presets_path, templates_dir_from_env

    presets = _load_presets(ROOT)
    if args.only:
        presets = [p for p in presets if str(p.get("id")) == args.only]
        if not presets:
            logger.error("No preset with id %r (check %s)", args.only, style_presets_path())
            return 1

    if args.limit > 0:
        presets = presets[: args.limit]

    out_root = templates_dir_from_env(args.data_root)
    out_root.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for preset in presets:
            await _generate_one(
                router=None,
                preset=preset,
                out_root=out_root,
                force=args.force,
                dry_run=True,
            )
        logger.info("Dry run finished.")
        return 0

    from llm import LLMRouter

    router = LLMRouter(config_path=str(Path(args.providers_config).resolve()))

    for preset in presets:
        await _generate_one(
            router=router,
            preset=preset,
            out_root=out_root,
            force=args.force,
            dry_run=args.dry_run,
        )

    preset_by_id = {str(p.get("id")): p for p in _load_presets(ROOT)}
    scanned: list[dict] = []
    if out_root.is_dir():
        for sub in sorted(out_root.iterdir()):
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            if not (sub / "index.html").is_file():
                continue
            pid = sub.name
            files = []
            for name in ("index.html", "style.css", "app.js"):
                if (sub / name).is_file():
                    files.append(name)
            meta = preset_by_id.get(pid) or {}
            scanned.append(
                {
                    "id": pid,
                    "title": str(meta.get("title") or pid),
                    "path": pid,
                    "files": files,
                }
            )

    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": time.time(),
                "preset_source": str(style_presets_path()),
                "templates": scanned,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("Wrote manifest %s (%d templates)", manifest_path, len(scanned))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate neural UI reference template pool")
    ap.add_argument(
        "--data-root",
        default=os.environ.get("AIFACTORY_DATA_ROOT", str(ROOT / "data")),
        help="Factory data root (default: AIFACTORY_DATA_ROOT or ./data)",
    )
    ap.add_argument(
        "--providers-config",
        default=os.environ.get("AIFACTORY_MODEL_PROVIDERS_PATH", str(ROOT / "data" / "config" / "model_providers.yaml")),
        help="Path to model_providers.yaml",
    )
    ap.add_argument("--only", help="Generate a single preset id from style_presets.json")
    ap.add_argument("--limit", type=int, default=0, help="Max presets to process (0 = all)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing template folders")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without calling LLM")
    args = ap.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
