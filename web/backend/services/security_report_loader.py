"""
Load pipeline security scan artifacts from disk.

SecurityAgent saves to ``/app/data/security/{product_id}/security_report.json`` with shape::
  {"report": {<scanner output>}, "scanned_at": ..., "scanner_version": ...}

Legacy paths may store the scanner output at the top level.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def unwrap_security_artifact(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the inner scanner payload (security_score, vulnerabilities, …)."""
    if not isinstance(raw, dict):
        return {}
    inner = raw.get("report")
    if isinstance(inner, dict) and (
        "security_score" in inner
        or "vulnerabilities" in inner
        or "grade" in inner
        or "summary" in inner
    ):
        return inner
    return raw


def load_security_report(product_id: str, *, data_root: str = "/app/data") -> Optional[dict[str, Any]]:
    """
    Load normalized security report dict for UI, or None.

    Tries canonical SecurityAgent path first, then legacy locations, then devops_result.
    """
    root = Path(data_root)

    candidates = [
        root / "security" / product_id / "security_report.json",
        root / "bugs" / product_id / "security_report.json",
        root / "state" / product_id / "security_report.json",
    ]

    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return unwrap_security_artifact(raw)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read security report %s: %s", path, e)

    devops = root / "state" / product_id / "devops_result.json"
    if devops.is_file():
        try:
            data = json.loads(devops.read_text(encoding="utf-8"))
            return {
                "product_id": product_id,
                "security_score": data.get("security_score", 0),
                "grade": data.get("grade", "N/A"),
                "findings": data.get("vulnerabilities", data.get("findings", [])),
                "vulnerabilities": data.get("vulnerabilities", data.get("findings", [])),
            }
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read devops result %s: %s", devops, e)

    bugs_dir = root / "bugs" / product_id
    if bugs_dir.is_dir():
        for f in bugs_dir.iterdir():
            if f.suffix == ".json" and "security" in f.name.lower():
                try:
                    raw = json.loads(f.read_text(encoding="utf-8"))
                    return unwrap_security_artifact(raw)
                except (OSError, json.JSONDecodeError):
                    continue

    return None
