"""
Auto-publish generated product code to a static host after the DevOps stage.

Reads toggles from ``general.auto_publish_*`` in ``/app/config.yaml`` (same as Admin → Settings).
Secrets **must** be supplied via environment variables — never commit tokens.

Supported providers:
  - ``vercel`` — requires ``VERCEL_TOKEN``; optional ``VERCEL_ORG_ID``, ``VERCEL_PROJECT_ID``
  - ``netlify`` — requires ``NETLIFY_AUTH_TOKEN``; optional ``NETLIFY_SITE_ID`` (otherwise draft URL)
  - ``cloudflare_pages`` — requires ``CLOUDFLARE_API_TOKEN``; ``general.auto_publish_cf_project_name`` + account

CLI tools must be on ``PATH`` inside the container/host (``vercel``, ``netlify``, ``wrangler``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from core.paths import data_root

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.environ.get("AIFACTORY_CONFIG_YAML", "/app/config.yaml"))

_URL_RE = re.compile(r"https://[^\s\)]+\.vercel\.app[^\s\)]*", re.I)
_NETLIFY_URL_RE = re.compile(r"https://[^\s\)]+\.netlify\.app[^\s\)]*", re.I)
_CF_URL_RE = re.compile(r"https://[^\s\)]+\.pages\.dev[^\s\)]*", re.I)


def _read_general() -> dict[str, Any]:
    try:
        if not CONFIG_PATH.is_file():
            return {}
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        g = raw.get("general")
        return g if isinstance(g, dict) else {}
    except Exception as e:
        logger.debug("auto_publish: could not read config: %s", e)
        return {}


def _extract_url(stdout: str, stderr: str, provider: str) -> str | None:
    blob = f"{stdout}\n{stderr}"
    if provider == "vercel":
        m = _URL_RE.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
    if provider == "netlify":
        m = _NETLIFY_URL_RE.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
        for line in blob.splitlines():
            line = line.strip()
            if line.startswith("https://") and "netlify" in line:
                return line.split()[0].rstrip(".)'`\"")
    if provider == "cloudflare_pages":
        m = _CF_URL_RE.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
    for pat in (_URL_RE, _NETLIFY_URL_RE, _CF_URL_RE):
        m = pat.search(blob)
        if m:
            return m.group(0).rstrip(".)'`\"")
    return None


def try_publish_after_devops(product_id: str) -> dict[str, Any]:
    """Sync helper (call via asyncio.to_thread from pipeline worker)."""
    general = _read_general()
    if not general.get("auto_publish_enabled"):
        return {"ok": False, "skipped": True, "reason": "disabled"}

    provider = str(general.get("auto_publish_provider") or "none").strip().lower()
    if provider in ("", "none", "off", "false"):
        return {"ok": False, "skipped": True, "reason": "provider_none"}

    code_dir = Path(data_root()) / "code" / product_id
    if not code_dir.is_dir():
        return {"ok": False, "error": "code_dir_missing", "path": str(code_dir)}

    out_path = Path(data_root()) / "state" / product_id / "auto_publish.json"
    env = os.environ.copy()

    cmd: list[str]
    timeout = int(os.environ.get("AIFACTORY_AUTO_PUBLISH_TIMEOUT_SEC", "900"))

    try:
        if provider == "vercel":
            token = env.get("VERCEL_TOKEN", "").strip()
            if not token:
                err = "VERCEL_TOKEN not set"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            vercel_bin = shutil.which("vercel")
            if not vercel_bin:
                err = "vercel CLI not found on PATH (npm i -g vercel)"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            cmd = [vercel_bin, str(code_dir), "--prod", "--yes", "--token", token]
            if env.get("VERCEL_ORG_ID"):
                cmd.extend(["--scope", env["VERCEL_ORG_ID"]])

        elif provider == "netlify":
            auth = env.get("NETLIFY_AUTH_TOKEN", "").strip()
            if not auth:
                err = "NETLIFY_AUTH_TOKEN not set"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            netlify_bin = shutil.which("netlify")
            if not netlify_bin:
                err = "netlify CLI not found on PATH"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            cmd = [netlify_bin, "deploy", "--prod", "--dir", str(code_dir), "--auth", auth]
            site = str(general.get("auto_publish_netlify_site_id") or "").strip()
            if site:
                cmd.extend(["--site", site])

        elif provider == "cloudflare_pages":
            tok = env.get("CLOUDFLARE_API_TOKEN", "").strip()
            if not tok:
                err = "CLOUDFLARE_API_TOKEN not set"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            wrangler_bin = shutil.which("wrangler")
            if not wrangler_bin:
                err = "wrangler CLI not found on PATH (npm i -g wrangler)"
                _write_result(out_path, product_id, provider, ok=False, error=err)
                return {"ok": False, "error": err}
            proj = str(general.get("auto_publish_cf_project_name") or "").strip()
            if not proj:
                proj = f"aifactory-{product_id.replace('prod-', '')[:12]}"
            account = env.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
            cmd = [wrangler_bin, "pages", "deploy", str(code_dir), "--project-name", proj]
            if account:
                cmd.extend(["--account-id", account])
        else:
            return {"ok": False, "error": f"unknown_provider:{provider}"}

        logger.info("Auto-publish %s → %s (%s)", product_id, provider, " ".join(cmd[:6]))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        url = _extract_url(proc.stdout, proc.stderr, provider)
        ok = proc.returncode == 0 and bool(url)
        payload = {
            "ok": ok,
            "product_id": product_id,
            "provider": provider,
            "exit_code": proc.returncode,
            "published_url": url,
            "stdout_tail": (proc.stdout or "")[-8000:],
            "stderr_tail": (proc.stderr or "")[-8000:],
            "ts": time.time(),
        }
        if proc.returncode != 0:
            payload["error"] = "cli_failed"
        elif not url:
            payload["error"] = "url_not_detected"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        if ok:
            logger.info("Auto-publish OK %s → %s", product_id, url)
        else:
            logger.warning(
                "Auto-publish incomplete %s rc=%s url=%s",
                product_id,
                proc.returncode,
                url,
            )
        return payload
    except subprocess.TimeoutExpired:
        err = f"timeout_after_{timeout}s"
        _write_result(out_path, product_id, provider, ok=False, error=err)
        return {"ok": False, "error": err}
    except Exception as e:
        logger.exception("Auto-publish failed for %s", product_id)
        _write_result(out_path, product_id, provider, ok=False, error=str(e))
        return {"ok": False, "error": str(e)}


def _write_result(path: Path, product_id: str, provider: str, ok: bool, error: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ok": ok,
                "product_id": product_id,
                "provider": provider,
                "error": error,
                "ts": time.time(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
