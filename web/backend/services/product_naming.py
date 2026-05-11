"""
Product naming service
======================
Generates human-readable, unique storefront names and marks template items.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _clean_name(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = re.sub(r"[™®]", "", s)
    return s[:120].strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _derive_from_idea(idea: str, default_prefix: str = "Studio") -> str:
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", (idea or "")) if len(w) >= 3]
    if not words:
        return f"{default_prefix} Product"
    return " ".join(w.capitalize() for w in words[:3])


def _is_bad_generated_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return (
        not n
        or n.startswith("product prod-")
        or n.startswith("prod-")
        or n in {"product", "new product", "untitled product"}
    )


# Collision disambiguation sometimes produced "ABCD" tokens; LLMs also echo them → spam titles.
_HEX_TOKEN = re.compile(r"^[0-9A-Fa-f]{4}$")


def sanitize_product_display_name(name: str) -> str:
    """
    Collapse accidental duplication (same 4-hex token repeated) and consecutive duplicate words.
    Safe for storefront titles resolved from spec/marketing.
    """
    s = _clean_name(name)
    parts = [p for p in s.split() if p]
    out: list[str] = []
    for p in parts:
        if out and p == out[-1]:
            continue
        out.append(p)
    s = " ".join(out)
    # Strip runs of 3+ separated 4-char hex-like tokens (hash suffix echo / model glitch)
    s = re.sub(r"(?:\s+\b[0-9A-Fa-f]{4}\b){3,}", "", s, flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s[:120].strip()


def _name_has_spam_pattern(name: str) -> bool:
    """Repeated hex-ish tokens or copy-paste loops — block marketplace listing."""
    s = (name or "").strip()
    if not s:
        return False
    parts = s.split()
    if len(parts) >= 5:
        short_hexish = sum(1 for p in parts if _HEX_TOKEN.match(p))
        if short_hexish >= 3:
            return True
    # Same token repeated 4+ times (any token)
    if len(parts) >= 8:
        counts: dict[str, int] = {}
        for p in parts:
            counts[p] = counts.get(p, 0) + 1
        if max(counts.values()) >= 4:
            return True
    return False


def is_placeholder_product_name(name: str) -> bool:
    """Public helper for strict naming-quality gates."""
    raw = (name or "").strip()
    if _name_has_spam_pattern(raw):
        return True
    cleaned = sanitize_product_display_name(raw)
    if _name_has_spam_pattern(cleaned):
        return True
    return _is_bad_generated_name(cleaned)


def is_template_product(product: dict[str, Any], spec: dict[str, Any] | None, marketing: dict[str, Any] | None) -> bool:
    blob = " ".join(
        [
            str((product or {}).get("idea", "")),
            json.dumps(spec or {}, ensure_ascii=False),
            json.dumps(marketing or {}, ensure_ascii=False),
        ]
    ).lower()
    return any(k in blob for k in ("template", "starter", "boilerplate", "landing template"))


def _existing_names_from_specs(data_root: str = "/app/data") -> set[str]:
    root = Path(data_root) / "specs"
    out: set[str] = set()
    if not root.exists():
        return out
    for p in root.glob("*/specification.json"):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            spec = raw.get("specification") if isinstance(raw, dict) else {}
            nm = _clean_name(str((spec or {}).get("product_name", "")))
            if nm:
                out.add(_slug(nm))
        except Exception:
            continue
    return out


def _web_exact_name_exists(name: str) -> bool:
    """
    Optional best-effort public search check.
    Uses Wikipedia OpenSearch endpoint as a lightweight collision signal.
    Any network errors are treated as "unknown" (non-blocking).
    """
    q = urllib.parse.quote(name)
    url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={q}&limit=5&namespace=0&format=json"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as r:  # nosec B310
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
        titles = [str(x).strip().lower() for x in (payload[1] if isinstance(payload, list) and len(payload) > 1 else [])]
        return name.strip().lower() in titles
    except Exception:
        return False


def resolve_product_name(
    *,
    product_id: str,
    product: dict[str, Any],
    spec: dict[str, Any] | None,
    marketing: dict[str, Any] | None,
    used_names: set[str] | None = None,
    data_root: str = "/app/data",
) -> tuple[str, bool]:
    """Return (resolved_name, is_template)."""
    used = set(used_names or set())
    used.update(_existing_names_from_specs(data_root=data_root))

    raw_candidates = [
        str((marketing or {}).get("product_name", "")),
        str((spec or {}).get("product_name", "")),
    ]
    name = ""
    for c in raw_candidates:
        cleaned = _clean_name(c)
        if cleaned and not _is_bad_generated_name(cleaned):
            name = cleaned
            break
    if not name:
        name = _derive_from_idea(str((product or {}).get("idea", "")))

    template = is_template_product(product, spec, marketing)
    if template and not name.lower().startswith("template:"):
        name = f"Template: {name}"

    base_slug = _slug(name)
    if not base_slug:
        base_slug = _slug(_derive_from_idea(str((product or {}).get("idea", ""))))
        name = _derive_from_idea(str((product or {}).get("idea", "")))

    collision = base_slug in used or _web_exact_name_exists(name)
    if collision:
        # Short numeric disambiguator — avoids ugly 4-hex fragments users read as garbage.
        h = hashlib.sha1(product_id.encode("utf-8")).hexdigest()
        tail = str(int(h[:8], 16) % 900 + 100)
        name = f"{name} ({tail})"
        base_slug = _slug(name)

    name = sanitize_product_display_name(name)

    used.add(base_slug)
    if used_names is not None:
        used_names.add(base_slug)
    return name, template
