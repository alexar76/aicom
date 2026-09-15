"""Selective publish of factory products into alexar76/aicom-products."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.config_merge import load_merged_config
from core.github_catalog import github_house_gate_active, github_pat_configured
from core.paths import code_dir, config_path, data_root

logger = logging.getLogger(__name__)

CATALOG_REMOTE = "https://github.com/alexar76/aicom-products.git"
SCRIPT_REL = Path("scripts/publish_factory_product_catalog.sh")
CONFIG_PATH = config_path()


def resolve_product_live_url(product_id: str) -> str:
    """Public demo URL (Vercel etc.) from auto_publish / product extras — https only."""
    candidates: list[Path] = []
    try:
        candidates.append(Path(data_root()) / "state" / product_id / "auto_publish.json")
    except Exception:
        pass
    candidates.append(Path("/app/data/state") / product_id / "auto_publish.json")

    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        for key in ("vercel_url", "published_url", "url", "public_url"):
            val = raw.get(key)
            if isinstance(val, str) and val.startswith("https://"):
                return val.strip()
        lg = raw.get("live_gate")
        if isinstance(lg, dict):
            val = lg.get("url")
            if isinstance(val, str) and val.startswith("https://"):
                return val.strip()
    return ""


def _read_general() -> dict[str, Any]:
    try:
        raw = load_merged_config(CONFIG_PATH)
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as exc:
        logger.debug("product_catalog: could not read config: %s", exc)
        return {}


def _allowlist(general: dict[str, Any] | None = None) -> set[str]:
    g = general if general is not None else _read_general()
    raw = str(g.get("product_catalog_allowlist") or "").strip()
    if not raw:
        return set()
    return {p.strip() for p in raw.split(",") if p.strip()}


def catalog_enabled() -> bool:
    return bool(_read_general().get("product_catalog_enabled", False))


def product_on_allowlist(product_id: str) -> bool:
    allowed = _allowlist()
    return bool(allowed) and product_id in allowed


def github_house_ok(product_id: str, general: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Hard gate: README badge markers + CONTRIBUTING.md when the GitHub house gate is active."""
    g = general if general is not None else _read_general()
    if not github_house_gate_active(g):
        return True, ""
    root = code_dir(product_id)
    readme = root / "README.md"
    contributing = root / "CONTRIBUTING.md"
    if not contributing.is_file():
        return False, "missing CONTRIBUTING.md"
    if not readme.is_file():
        return False, "missing README.md"
    text = readme.read_text(encoding="utf-8", errors="replace")
    if "aicom-readme-badges" not in text and "docs/badges/" not in text.lower():
        return False, "README missing badge row (aicom-readme-badges / docs/badges/)"
    from web.backend.services.github_house_assets import missing_readme_assets

    dead = missing_readme_assets(root, text)
    if dead:
        return False, "dead README images: " + ", ".join(dead)
    return True, ""


def try_publish_product_catalog(product_id: str) -> dict:
    """Non-blocking catalog push for one allowlisted product."""
    general = _read_general()
    result: dict = {
        "enabled": bool(general.get("product_catalog_enabled", False)),
        "github_ready": bool(general.get("product_catalog_enabled")) and github_pat_configured(),
        "product_id": product_id,
        "ok": False,
        "skipped": False,
        "detail": "",
    }
    if not general.get("product_catalog_enabled"):
        result["skipped"] = True
        result["detail"] = "product_catalog_enabled=false"
        return result
    if not github_pat_configured():
        result["skipped"] = True
        result["detail"] = "github_not_configured: set GH_PAT/GITHUB_TOKEN before catalog publish"
        logger.warning("product catalog skipped for %s: GitHub PAT not configured", product_id)
        return result
    allowed = _allowlist(general)
    if product_id not in allowed:
        result["skipped"] = True
        result["detail"] = "not on product_catalog_allowlist"
        return result
    ok, reason = github_house_ok(product_id, general)
    if not ok:
        result["detail"] = f"github_house_gate: {reason}"
        logger.warning("product catalog blocked for %s: %s", product_id, reason)
        return result

    token = (os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or "").strip()

    candidates: list[Path] = [
        Path(__file__).resolve().parents[3],
        Path("/app"),
        Path("/root/claudecode/aicom"),
    ]
    try:
        candidates.insert(1, Path(data_root()).resolve().parent)
    except Exception:
        pass

    repo_root: Path | None = None
    for c in candidates:
        if c and (c / SCRIPT_REL).is_file():
            repo_root = c
            break
    if repo_root is None:
        script = shutil.which("publish_factory_product_catalog.sh")
        if not script:
            result["detail"] = "publish_factory_product_catalog.sh not found"
            return result
        cmd = [script]
    else:
        cmd = ["bash", str(repo_root / SCRIPT_REL)]

    src = code_dir(product_id)
    if not src.is_dir():
        result["detail"] = f"missing code dir {src}"
        return result

    env = os.environ.copy()
    env["GH_PAT"] = token
    env["AICOM_PRODUCTS_CATALOG_REMOTE"] = CATALOG_REMOTE
    cmd += ["--product", product_id, "--source", str(src)]
    live = resolve_product_live_url(product_id)
    if live:
        cmd += ["--live-url", live]
        result["live_url"] = live
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root) if repo_root else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except Exception as exc:
        result["detail"] = str(exc)
        logger.exception("product catalog publish failed for %s", product_id)
        return result

    result["ok"] = proc.returncode == 0
    result["detail"] = (proc.stdout or proc.stderr or "")[-2000:]
    if not result["ok"]:
        logger.warning(
            "product catalog publish rc=%s for %s: %s",
            proc.returncode,
            product_id,
            result["detail"][-500:],
        )
    else:
        logger.info("product catalog published %s", product_id)
    return result
