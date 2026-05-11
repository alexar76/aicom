"""
Optional neural-generated UI reference templates for the Developer Agent.

Templates are produced offline by ``scripts/generate_reference_templates.py`` and stored
under ``AIFACTORY_REFERENCE_TEMPLATES_DIR`` (default: ``<data_root>/reference_templates``).
Bundled style directions live in ``reference_templates/style_presets.json`` at repo root.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

TEMPLATE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
ALLOWED_TEMPLATE_RELATIVE_FILES = frozenset({"index.html", "style.css", "app.js"})
RESERVED_TEMPLATE_IDS = frozenset({"manifest"})

# (mtime, general dict) per resolved config path — invalidates when file changes on disk
_CONFIG_GENERAL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _config_yaml_path() -> Path:
    return Path(os.environ.get("AIFACTORY_CONFIG_YAML", "/app/config.yaml"))


def _general_from_config() -> dict[str, Any]:
    """Load ``general`` from config.yaml. Env vars ``AIFACTORY_REFERENCE_*`` override these (see callers)."""
    p = _config_yaml_path()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {}
    key = str(p.resolve())
    hit = _CONFIG_GENERAL_CACHE.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        out: dict[str, Any] = {}
        _CONFIG_GENERAL_CACHE[key] = (mtime, out)
        return out
    g = raw.get("general") if isinstance(raw, dict) else {}
    out = g if isinstance(g, dict) else {}
    _CONFIG_GENERAL_CACHE[key] = (mtime, out)
    return out


def _env_or_bool(env_key: str, yaml_key: str, *, default: bool = False) -> bool:
    if env_key in os.environ:
        return os.environ[env_key].strip().lower() in ("1", "true", "yes", "on")
    return bool(_general_from_config().get(yaml_key, default))


def _env_or_str(env_key: str, yaml_key: str, *, default: str = "") -> str:
    if env_key in os.environ:
        return os.environ.get(env_key, "").strip()
    v = _general_from_config().get(yaml_key)
    if v is None:
        return default
    return str(v).strip()


def _env_or_int(env_key: str, yaml_key: str, *, default: int) -> int:
    if env_key in os.environ:
        try:
            raw = os.environ.get(env_key, "").strip()
            return int(raw) if raw else default
        except ValueError:
            return default
    v = _general_from_config().get(yaml_key)
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def style_presets_path() -> Path:
    return _repo_root() / "reference_templates" / "style_presets.json"


def templates_dir_from_env(data_root: str | Path | None = None) -> Path:
    raw = _env_or_str(
        "AIFACTORY_REFERENCE_TEMPLATES_DIR",
        "reference_templates_dir",
        default="",
    )
    if raw:
        return Path(raw)
    dr = data_root or os.environ.get("AIFACTORY_DATA_ROOT") or "/app/data"
    return Path(dr) / "reference_templates"


def reference_templates_enabled() -> bool:
    """True when enabled in Admin Settings (config.yaml) or ``AIFACTORY_REFERENCE_TEMPLATES_ENABLED``."""
    return _env_or_bool("AIFACTORY_REFERENCE_TEMPLATES_ENABLED", "reference_templates_enabled", default=False)


def reference_template_selection_mode() -> str:
    v = _env_or_str(
        "AIFACTORY_REFERENCE_TEMPLATE_MODE",
        "reference_template_mode",
        default="random",
    )
    return (v or "random").strip().lower()


def reference_template_fixed_id() -> str:
    return _env_or_str("AIFACTORY_REFERENCE_TEMPLATE_ID", "reference_template_id", default="")


def reference_prompt_max_chars() -> int:
    return max(
        2000,
        _env_or_int(
            "AIFACTORY_REFERENCE_PROMPT_MAX_CHARS",
            "reference_prompt_max_chars",
            default=14000,
        ),
    )


def load_style_presets() -> list[dict[str, Any]]:
    p = style_presets_path()
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("reference_templates: cannot load style_presets.json: %s", e)
        return []


def load_manifest(templates_root: Path) -> dict[str, Any]:
    mp = templates_root / "manifest.json"
    if not mp.is_file():
        return {}
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def folder_display_title(folder: Path, folder_name: str, preset_by_id: dict[str, Any]) -> str:
    """Title from reference.meta.json, else style_presets.json, else folder name."""
    meta_path = folder / "reference.meta.json"
    if meta_path.is_file():
        try:
            j = json.loads(meta_path.read_text(encoding="utf-8"))
            t = str(j.get("title") or "").strip()
            if t:
                return t
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    pr = preset_by_id.get(folder_name) or {}
    return str(pr.get("title") or folder_name)


def validate_template_id(template_id: str) -> str:
    tid = (template_id or "").strip()
    if not tid or not TEMPLATE_ID_RE.match(tid):
        raise ValueError("template_id must be a lowercase slug (e.g. my-brand-shell)")
    if tid.startswith("."):
        raise ValueError("invalid template id")
    if tid in RESERVED_TEMPLATE_IDS:
        raise ValueError("reserved template id")
    return tid


def max_template_file_bytes() -> int:
    try:
        return max(4096, int(os.environ.get("AIFACTORY_REFERENCE_TEMPLATE_MAX_BYTES", "524288")))
    except ValueError:
        return 524288


def rebuild_reference_manifest(templates_root: Path) -> dict[str, Any]:
    """Rewrite manifest.json from folders containing index.html."""
    templates_root.mkdir(parents=True, exist_ok=True)
    preset_by_id = {str(p.get("id")): p for p in load_style_presets()}
    scanned: list[dict[str, Any]] = []
    try:
        for sub in sorted(templates_root.iterdir()):
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            if not (sub / "index.html").is_file():
                continue
            pid = sub.name
            title = folder_display_title(sub, pid, preset_by_id)
            fnames = [n for n in ("index.html", "style.css", "app.js") if (sub / n).is_file()]
            scanned.append({"id": pid, "title": title, "path": pid, "files": fnames})
    except OSError as e:
        logger.warning("rebuild_reference_manifest: scan failed: %s", e)

    payload = {
        "version": 1,
        "generated_at": time.time(),
        "preset_source": str(style_presets_path()),
        "templates": scanned,
    }
    mp = templates_root / "manifest.json"
    mp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def upsert_reference_template_upload(
    data_root: str | Path | None,
    template_id: str,
    title: str | None,
    files: list[tuple[str, str]],
) -> dict[str, Any]:
    """
    Write or replace one template folder (admin upload). Requires index.html.
    ``files`` are (relative_path, utf-8 content).
    """
    tid = validate_template_id(template_id)
    root = templates_dir_from_env(data_root)
    root.mkdir(parents=True, exist_ok=True)

    max_b = max_template_file_bytes()
    seen_paths: set[str] = set()
    total_bytes = 0

    for rel, content in files:
        rel_norm = str(rel or "").strip().replace("\\", "/").lstrip("/")
        if not rel_norm or rel_norm not in ALLOWED_TEMPLATE_RELATIVE_FILES:
            raise ValueError(f"file not allowed: {rel!r} (use index.html, style.css, app.js)")
        if rel_norm in seen_paths:
            raise ValueError(f"duplicate path: {rel_norm}")
        seen_paths.add(rel_norm)
        if rel_norm == "index.html" and not (content or "").strip():
            raise ValueError("index.html must not be empty")
        raw = (content or "").encode("utf-8")
        total_bytes += len(raw)
        if len(raw) > max_b:
            raise ValueError(f"file too large: {rel_norm} (max {max_b} bytes)")
    if total_bytes > max_b * 4:
        raise ValueError("total upload too large")

    if "index.html" not in seen_paths:
        raise ValueError("index.html is required")

    dest = root / tid
    if dest.is_dir():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    display_title = (title or "").strip() or tid
    meta = {"title": display_title, "source": "admin_upload"}
    (dest / "reference.meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for rel, content in files:
        rel_norm = str(rel or "").strip().replace("\\", "/").lstrip("/")
        fp = dest / rel_norm
        fp.write_text(content, encoding="utf-8")

    return rebuild_reference_manifest(root)


def delete_reference_template_dir(data_root: str | Path | None, template_id: str) -> bool:
    tid = validate_template_id(template_id)
    root = templates_dir_from_env(data_root)
    dest = root / tid
    if not dest.is_dir():
        return False
    shutil.rmtree(dest)
    rebuild_reference_manifest(root)
    return True


def list_reference_templates_catalog(data_root: str | Path | None = None) -> list[dict[str, Any]]:
    """
    Templates available under the resolved reference directory (manifest + orphan folders with index.html).
    Used by Admin Settings to populate the template picker.
    """
    root = templates_dir_from_env(data_root)
    if not root.is_dir():
        return []

    manifest = load_manifest(root)
    preset_by_id = {str(p.get("id")): p for p in load_style_presets()}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    for t in manifest.get("templates") or []:
        if not isinstance(t, dict):
            continue
        path = str(t.get("path") or "").strip()
        if not path or path in seen:
            continue
        sub = root / path
        if not (sub / "index.html").is_file():
            continue
        seen.add(path)
        files = t.get("files")
        file_list = files if isinstance(files, list) else []
        disp = str(t.get("title") or "").strip() or folder_display_title(sub, path, preset_by_id)
        out.append(
            {
                "id": str(t.get("id") or path),
                "title": disp,
                "path": path,
                "files": [str(x) for x in file_list],
            }
        )

    try:
        for sub in sorted(root.iterdir()):
            if not sub.is_dir() or sub.name.startswith(".") or sub.name in seen:
                continue
            if not (sub / "index.html").is_file():
                continue
            seen.add(sub.name)
            fnames = [
                n for n in ("index.html", "style.css", "app.js") if (sub / n).is_file()
            ]
            out.append(
                {
                    "id": sub.name,
                    "title": folder_display_title(sub, sub.name, preset_by_id),
                    "path": sub.name,
                    "files": fnames,
                }
            )
    except OSError:
        pass

    return sorted(out, key=lambda x: (str(x.get("title") or ""), str(x.get("path") or "")))


def discover_template_paths(templates_root: Path, manifest: dict[str, Any]) -> list[str]:
    """Folder names under templates_root that contain index.html (manifest first, then scan)."""
    valid_paths: list[str] = []
    seen: set[str] = set()
    for t in manifest.get("templates") or []:
        if not isinstance(t, dict):
            continue
        path = str(t.get("path") or "").strip()
        if not path or path in seen:
            continue
        if (templates_root / path / "index.html").is_file():
            seen.add(path)
            valid_paths.append(path)
    try:
        for sub in sorted(templates_root.iterdir()):
            if not sub.is_dir() or sub.name.startswith(".") or sub.name in seen:
                continue
            if (sub / "index.html").is_file():
                seen.add(sub.name)
                valid_paths.append(sub.name)
    except OSError:
        pass
    return valid_paths


def _tokenize(text: str) -> set[str]:
    return {w for w in re.split(r"[^\w]+", text.lower()) if len(w) >= 4}


def _score_preset_match(spec_text: str, preset: dict[str, Any]) -> float:
    blob = " ".join(
        str(preset.get(k) or "")
        for k in ("id", "title", "neural_prompt")
    ).lower()
    words = _tokenize(spec_text)
    if not words:
        return 0.0
    pb = set(_tokenize(blob))
    hit = len(words & pb)
    return hit / max(1, len(words))


def pick_template_folder_name(
    templates_root: Path,
    *,
    product_id: str,
    specification: dict[str, Any],
    admin_instructions: str,
    manifest: dict[str, Any],
) -> Optional[str]:
    """Resolve which generated template directory to use (folder name = preset id)."""
    valid_paths = discover_template_paths(templates_root, manifest)

    if not valid_paths:
        return None

    mode = reference_template_selection_mode()
    fixed = reference_template_fixed_id()
    if mode == "fixed" and fixed:
        return fixed if fixed in valid_paths else None

    if mode == "match_spec":
        parts = [
            admin_instructions or "",
            json.dumps(specification, ensure_ascii=False),
            str(specification.get("idea") or ""),
        ]
        spec_text = "\n".join(parts)
        presets = load_style_presets()
        best_path: Optional[str] = None
        best_score = -1.0
        for pr in presets:
            pid = str(pr.get("id") or "").strip()
            if pid not in valid_paths:
                continue
            sc = _score_preset_match(spec_text, pr)
            if sc > best_score:
                best_score = sc
                best_path = pid
        if best_path is not None and best_score > 0:
            return best_path
        # fall through to random if no overlap

    if mode == "round_robin":
        state_path = templates_root / "._selection_state.json"
        idx = 0
        try:
            if state_path.is_file():
                st = json.loads(state_path.read_text(encoding="utf-8"))
                idx = int(st.get("round_robin_index", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            idx = 0
        chosen = valid_paths[idx % len(valid_paths)]
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps({"round_robin_index": idx + 1}, indent=0),
                encoding="utf-8",
            )
        except OSError:
            pass
        return chosen

    # random (default): stable per product_id
    h = hashlib.sha256(product_id.encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(valid_paths)
    return valid_paths[idx]


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 20] + "\n… [truncated]\n"


def build_reference_template_prompt_block(
    *,
    product_id: str,
    specification: dict[str, Any],
    admin_instructions: str,
    data_root: str | Path,
) -> str:
    """
    Returns text to append to the Developer prompt, or empty string if disabled / missing data.
    """
    if not reference_templates_enabled():
        return ""

    root = templates_dir_from_env(data_root)
    manifest = load_manifest(root)
    folder = pick_template_folder_name(
        root,
        product_id=product_id,
        specification=specification if isinstance(specification, dict) else {},
        admin_instructions=admin_instructions or "",
        manifest=manifest,
    )
    if not folder:
        logger.debug(
            "reference_templates: no template selected (manifest missing or empty under %s)",
            root,
        )
        return ""

    sub = root / folder
    if not sub.is_dir():
        logger.warning("reference_templates: folder missing on disk: %s", sub)
        return ""

    budget = reference_prompt_max_chars()
    # Prefer index.html, then CSS, then JS
    parts: list[str] = []
    meta_line = f"(reference template id: **{folder}** — mirror interaction/visual patterns, not copy marketing copy)\n"

    index_p = sub / "index.html"
    css_p = sub / "style.css"
    js_p = sub / "app.js"

    chunk_budget = [int(budget * 0.55), int(budget * 0.28), int(budget * 0.17)]

    if index_p.is_file():
        try:
            parts.append(
                "=== FILE: index.html ===\n"
                + _truncate(index_p.read_text(encoding="utf-8", errors="replace"), chunk_budget[0])
            )
        except OSError:
            pass
    if css_p.is_file():
        try:
            parts.append(
                "=== FILE: style.css ===\n"
                + _truncate(css_p.read_text(encoding="utf-8", errors="replace"), chunk_budget[1])
            )
        except OSError:
            pass
    if js_p.is_file():
        try:
            parts.append(
                "=== FILE: app.js ===\n"
                + _truncate(js_p.read_text(encoding="utf-8", errors="replace"), chunk_budget[2])
            )
        except OSError:
            pass

    if not parts:
        return ""

    body = "\n\n".join(parts)
    if len(body) > budget:
        body = _truncate(body, budget)

    return (
        "\n=== NEURAL UI REFERENCE SHELL (optional factory pool — copy patterns & craft level) ===\n"
        + meta_line
        + "Study structure: tokens, motion, SVG, responsive nav, states. Adapt branding to THIS product.\n\n"
        + body
        + "\n=== END NEURAL UI REFERENCE ===\n"
    )
