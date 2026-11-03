"""Hub wrapper: run ACEX AI auditor against catalog rows + optional MOMUS bulletin."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1]):
        if (base / "acex").is_dir():
            return base
    return here.parents[2]


_ROOT = _repo_root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from acex.integrations.ai_audit import (
        AUDITOR_ID,
        AUDITOR_KIND,
        MIN_AUDIT_SCORE_BPS,
        build_pack,
        fetch_momus_findings,
    )
except ImportError:  # pragma: no cover - pip-only hub
    AUDITOR_ID = "ai-auditor:acex-v1"
    AUDITOR_KIND = "ai-agent"
    MIN_AUDIT_SCORE_BPS = 7000
    build_pack = None  # type: ignore[assignment]
    fetch_momus_findings = None  # type: ignore[assignment]


def _truthy(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def require_ai_audit() -> bool:
    """HTTP / auto-list ALP gate. Default ON — a human score is not sufficient."""
    return _truthy("ACEX_REQUIRE_AI_AUDIT", "1")


def momus_findings_url() -> str:
    return os.getenv("ACEX_MOMUS_FINDINGS_URL", "https://momus.modelmarket.dev/findings").strip()


def audit_capabilities(product_id: str, capabilities: list[Any]) -> dict[str, Any]:
    if build_pack is None:
        return {
            "error": "ai_audit_unavailable",
            "verdict": "reject",
            "score_bps": 0,
            "reasons": ["acex.integrations.ai_audit not importable"],
        }
    findings: list[dict[str, Any]] = []
    url = momus_findings_url()
    if url and fetch_momus_findings is not None:
        findings = fetch_momus_findings(url)
    return build_pack(product_id, capabilities, momus_findings=findings)


def _federated_search_caps(product_id: str) -> list[dict[str, Any]]:
    """Hub SQLite may not hold federated ATLAS rows; search is live evidence."""
    if os.getenv("ACEX_AI_AUDIT_FEDERATED_SEARCH", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return []
    url = os.getenv(
        "ACEX_HUB_SEARCH_URL",
        "https://modelmarket.dev/ai-market/v2/search",
    ).strip()
    if not url:
        return []
    try:
        import json
        import urllib.parse
        import urllib.request

        q = urllib.parse.urlencode({"intent": product_id, "budget": "5"})
        req = urllib.request.Request(f"{url}?{q}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    matches = payload.get("matches") or []
    return [m for m in matches if isinstance(m, dict) and str(m.get("product_id") or "") == product_id]


def caps_for_product(db: Any, product_id: str) -> list[Any]:
    pid = (product_id or "").strip()
    if not pid:
        return []
    out: list[Any] = []
    if db is not None:
        try:
            rows = db.list_capabilities(limit=1000)
        except TypeError:
            rows = db.list_capabilities()
        except Exception:
            rows = []
        for c in rows or []:
            cid = getattr(c, "product_id", None)
            if cid is None and isinstance(c, dict):
                cid = c.get("product_id")
            if str(cid or "") == pid:
                out.append(c)
    if out:
        return out
    return _federated_search_caps(pid)
