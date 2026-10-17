"""The small, explicitly enabled code-diagnosis contract used by the factory."""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from core.procurement_store import micros

CONTRACT = "aicom.diagnosis/1"
MAX_RESPONSE_BYTES = 128_000
_SECRET = re.compile(
    r"-----BEGIN .*PRIVATE KEY-----|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{16,}|"
    r"(?i:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"\n]{8,}['\"]"
)
_NON_CODE_FAILURE = re.compile(
    r"payment_authorization|payment_required|quota.exhaust|budget.exceed|"
    r"missing.spec|spec.missing|rate.limit|provider.outage|live_mesh_unreachable", re.I
)
_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs", ".html", ".css"}
_PRIVATE_PARTS = {".git", ".aws", ".ssh", "secrets", "node_modules", ".venv", "__pycache__"}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class PurchasePolicy:
    hub_url: str
    hub_key: str
    api_key: str
    providers: tuple[tuple[str, str], ...]
    share_globs: tuple[str, ...]
    per_call: int = 250_000
    per_product: int = 500_000
    per_day: int = 2_000_000
    completion_reserve: int = 500_000
    attempts: int = 2
    timeout: float = 40.0
    hub_pq_key: str = ""

    @classmethod
    def load(cls, root: Path) -> PurchasePolicy | None:
        path = root / "config" / "procurement.json"
        if not path.exists():
            return None
        raw = json.loads(path.read_text())
        if raw.get("enabled") is not True:
            return None
        url = str(raw.get("hub_url", "")).rstrip("/")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
                or parsed.query or parsed.fragment:
            raise ValueError("procurement hub_url must be an HTTPS URL without credentials/query")
        providers = tuple((str(p["product_id"]), str(p["capability_id"])) for p in raw["providers"])
        globs = tuple(str(p) for p in raw["share_globs"])
        api_key = os.environ.get("AIFACTORY_PROCUREMENT_API_KEY", "").strip()
        hub_key = str(raw.get("hub_public_key", "")).strip()
        if not providers or len(providers) > 10 or not globs or not api_key or not hub_key:
            raise ValueError("procurement needs providers, share_globs, pinned hub key and its dedicated API key")
        if len(base64.b64decode(hub_key, validate=True)) != 32:
            raise ValueError("procurement hub_public_key must be a base64 Ed25519 public key")
        amounts = {name: micros(raw.get(name, default)) for name, default in (
            ("per_call_usd", .25), ("per_product_usd", .5), ("per_day_usd", 2),
            ("completion_reserve_usd", .5),
        )}
        if any(value <= 0 for value in amounts.values()):
            raise ValueError("procurement limits and completion reserve must be positive")
        return cls(url, hub_key, api_key, providers, globs,
                   amounts["per_call_usd"], amounts["per_product_usd"], amounts["per_day_usd"],
                   amounts["completion_reserve_usd"], hub_pq_key=str(raw.get("hub_pq_public_key", "")))


def source_file(root: Path, relative: str, globs: tuple[str, ...]) -> str:
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts or "\\" in relative or not rel.parts \
            or any(p.startswith(".") or p in _PRIVATE_PARTS for p in rel.parts) \
            or rel.suffix not in _EXTENSIONS or not any(fnmatch.fnmatchcase(relative, g) for g in globs):
        raise ValueError("source outside the approved sharing scope")
    path = root / relative
    if any((root.joinpath(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)):
        raise ValueError("source symlinks are not shared")
    path.resolve().relative_to(root.resolve())
    with path.open("rb") as stream:
        data = stream.read(16_001)
    if len(data) > 16_000:
        raise ValueError("source exceeds the diagnosis size limit")
    text = data.decode("utf-8")
    if _SECRET.search(text):
        raise ValueError("possible secret in source; refused sharing")
    return text


def build_requests(root: Path, findings: object, policy: PurchasePolicy) -> list[dict]:
    """Only file-bound QA findings; never ship an entire repository, logs or credentials."""
    if not isinstance(findings, list):
        return []
    requests = []
    for finding in findings[:100]:
        if not isinstance(finding, dict) or finding.get("severity") not in ("high", "critical"):
            continue
        path = str(finding.get("file") or "").strip()
        # QA emits both product-relative names and code/<product>/... (sometimes absolute).
        # Strip only this product's exact prefix, without resolving away traversal/symlinks.
        for prefix in (f"data/code/{root.name}/", f"code/{root.name}/"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        if PurePosixPath(path).is_absolute():
            try:
                path = str(PurePosixPath(path).relative_to(PurePosixPath(str(root))))
            except ValueError:
                continue
        path = str(PurePosixPath(path))
        title = str(finding.get("title") or finding.get("code") or "")[:400]
        if not title or _NON_CODE_FAILURE.search(title) or _SECRET.search(title):
            continue
        try:
            text = source_file(root, path, policy.share_globs)
        except (OSError, ValueError, UnicodeError):
            continue
        issue = digest({"file": path, "title": title})
        packet = {"contract": CONTRACT, "issue": issue,
                  "finding": {"file": path, "title": title, "severity": finding["severity"]},
                  "files": {path: text},
                  "acceptance": "Return a JSON object echoing contract, issue and fingerprint exactly. "
                                "Its diagnosis field must be an array of 1 to 5 objects, each containing "
                                "file (a supplied path), line (1-based integer), evidence (an exact non-empty "
                                "substring of that source line), explanation and suggested_check "
                                "(non-empty strings, each at most 2000 characters). "
                                "Do not execute commands or edit files."}
        packet["fingerprint"] = digest(packet)
        requests.append(packet)
    return sorted({p["issue"]: p for p in requests}.values(), key=lambda p: p["issue"])


def accept_report(packet: dict, report: object) -> dict:
    """Validate binding and a literal source citation. Semantic truth remains subject to QA."""
    if not isinstance(report, dict) or any(report.get(k) != packet[k] for k in ("contract", "issue", "fingerprint")):
        raise ValueError("diagnosis is not bound to this request")
    items = report.get("diagnosis")
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        raise ValueError("diagnosis needs one to five source-grounded findings")
    clean = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("malformed diagnosis")
        path, line = item.get("file"), item.get("line")
        if not isinstance(path, str) or path not in packet["files"] or type(line) is not int:
            raise ValueError("diagnosis cites an unshared file or invalid line")
        lines = packet["files"][path].splitlines()
        evidence = item.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip() or not 1 <= line <= len(lines) \
                or evidence.strip() not in lines[line - 1]:
            raise ValueError("diagnosis evidence does not match the source line")
        if any(not isinstance(item.get(k), str) or not 1 <= len(item[k]) <= 2000
               for k in ("explanation", "suggested_check")):
            raise ValueError("diagnosis requires explanation and a bounded suggested check")
        clean.append({k: item[k] for k in ("file", "line", "evidence", "explanation", "suggested_check")})
    return {"contract": CONTRACT, "issue": packet["issue"], "fingerprint": packet["fingerprint"],
            "diagnosis": clean}
