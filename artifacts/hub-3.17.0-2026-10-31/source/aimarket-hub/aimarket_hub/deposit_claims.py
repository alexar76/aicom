"""Hub-local single-use deposit claims (when the web on_chain module is not shipped).

The canonical registry lives in ``web.backend.services.ai_market_protocol.on_chain``.
The hub Docker image deliberately does not copy the web stack, so channel opens must
still be able to claim a deposit exclusively within this process. This module is that
fallback: same O_CREAT|O_EXCL semantics, stack-local directory only.

When both doors share a volume, set ``AIMARKET_DEPOSIT_CLAIMS_DIR`` and prefer the
web primitive; this fallback exists so a hub-only deployment can take real money.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEPOSIT_STACK_HUB = "aimarket-hub"
DEPOSIT_CLAIMS_DIR_ENV = "AIMARKET_DEPOSIT_CLAIMS_DIR"


def _canonical_chain(chain: str) -> str:
    return (chain or "").strip().lower()


def _canonical_tx(tx_hash: str) -> str:
    tx = (tx_hash or "").strip()
    body = tx[2:] if tx[:2].lower() == "0x" else tx
    if body and all(c in "0123456789abcdefABCDEF" for c in body):
        return "0x" + body.lower()
    return tx


def deposit_claim_key(chain: str, tx_hash: str) -> str:
    canonical = f"{_canonical_chain(chain)}|{_canonical_tx(tx_hash)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _usable_dir(path: Path) -> Path | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path if os.access(path, os.W_OK | os.X_OK) else None


def deposit_claims_dir(*, fallback_dir: str | Path | None = None) -> Path | None:
    configured = os.environ.get(DEPOSIT_CLAIMS_DIR_ENV, "").strip()
    if configured:
        got = _usable_dir(Path(configured))
        if got is None:
            logger.error(
                "%s=%s is not writable — refusing deposit claims",
                DEPOSIT_CLAIMS_DIR_ENV, configured,
            )
        return got
    if fallback_dir is None:
        return None
    local = _usable_dir(Path(fallback_dir))
    if local is None:
        return None
    logger.warning(
        "using hub-local deposit claims at %s (web on_chain not in image; "
        "set %s to share with the factory channel door)",
        local, DEPOSIT_CLAIMS_DIR_ENV,
    )
    return local


def _read_claim(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def claim_deposit(
    *,
    chain: str,
    tx_hash: str,
    stack: str,
    claim_id: str,
    amount_cents: int = 0,
    fallback_dir: str | Path | None = None,
) -> dict[str, Any]:
    d = deposit_claims_dir(fallback_dir=fallback_dir)
    if d is None:
        return {"ok": False, "error": "deposit_registry_unavailable"}
    path = d / f"{deposit_claim_key(chain, tx_hash)}.json"
    record = {
        "chain": _canonical_chain(chain),
        "tx_hash": _canonical_tx(tx_hash),
        "stack": stack,
        "claim_id": claim_id,
        "amount_cents": int(amount_cents or 0),
        "claimed_at": time.time(),
    }
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return {"ok": False, "error": "already_claimed", "claim": _read_claim(path)}
    except OSError as exc:
        logger.error("deposit claim write failed at %s: %s", path, exc)
        return {"ok": False, "error": "deposit_registry_unavailable"}
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        logger.error("deposit claim body write failed at %s: %s", path, exc)
        try:
            path.unlink()
        except OSError:
            pass
        return {"ok": False, "error": "deposit_registry_unavailable"}
    return {"ok": True, "claim": record, "dir": str(d)}


def release_deposit_claim(
    *,
    chain: str,
    tx_hash: str,
    stack: str,
    claim_id: str,
    fallback_dir: str | Path | None = None,
) -> bool:
    d = deposit_claims_dir(fallback_dir=fallback_dir)
    if d is None:
        return False
    path = d / f"{deposit_claim_key(chain, tx_hash)}.json"
    claim = _read_claim(path)
    if not claim:
        return False
    if claim.get("stack") != stack or claim.get("claim_id") != claim_id:
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False
