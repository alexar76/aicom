"""Publish a runnable full_software preview (compose / live API), not a static dump."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from core.paths import data_root
from core.public_site_url import resolve_public_site_url

logger = logging.getLogger(__name__)


def _absolute_view_url(view_path: str) -> str:
    origin = resolve_public_site_url().rstrip("/")
    path = (view_path or "").strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return origin + path


def _sandbox_starter():
    from web.backend.api.sandbox import _start_sandbox_for_product

    return _start_sandbox_for_product


def try_publish_working_app(product_id: str) -> dict[str, Any]:
    """
    Start the factory sandbox (docker compose when present, else uvicorn)
    and return a public URL that reverse-proxies the live stack.
    """
    out_path = Path(data_root()) / "state" / product_id / "auto_publish.json"
    try:
        start = _sandbox_starter()
    except Exception as exc:
        logger.exception("working_app_publish: cannot import sandbox start")
        return _fail(out_path, product_id, f"sandbox_import:{exc}")

    try:
        result = start(product_id, storefront=False)
    except Exception as exc:
        logger.exception("working_app_publish: sandbox start failed for %s", product_id)
        return _fail(out_path, product_id, f"sandbox_start:{exc}")

    if not isinstance(result, dict):
        return _fail(out_path, product_id, "sandbox_start_empty")

    compose = result.get("compose_preview") if isinstance(result.get("compose_preview"), dict) else {}
    preview_api = result.get("preview_api") if isinstance(result.get("preview_api"), dict) else {}
    sid = str(result.get("sandbox_id") or "").strip()
    view = str(result.get("url") or "").strip()
    compose_ok = str(compose.get("status") or "") == "ok" and bool(compose.get("proxy_prefix"))
    api_ok = bool(preview_api.get("enabled") and preview_api.get("proxy_prefix"))

    if not sid or not view:
        return _fail(
            out_path,
            product_id,
            "sandbox_no_url",
            extra={"compose_preview": compose, "preview_api": preview_api},
        )

    if not compose_ok and not api_ok:
        return _fail(
            out_path,
            product_id,
            "working_app_not_live",
            extra={
                "sandbox_id": sid,
                "compose_preview": compose,
                "preview_api": preview_api,
            },
        )

    url = _absolute_view_url(view)
    provider = "factory_compose" if compose_ok else "factory_uvicorn"
    payload = {
        "ok": True,
        "product_id": product_id,
        "provider": provider,
        "published_url": url,
        "sandbox_id": sid,
        "compose_preview": compose,
        "preview_api": preview_api,
        "ts": time.time(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("working_app_publish OK %s → %s (%s)", product_id, url, provider)
    return payload


def _fail(
    out_path: Path,
    product_id: str,
    error: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "product_id": product_id,
        "provider": "factory_compose",
        "error": error,
        "ts": time.time(),
    }
    if extra:
        payload.update(extra)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.warning("working_app_publish failed %s: %s", product_id, error)
    return payload
