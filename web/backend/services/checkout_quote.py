"""Authenticate immutable checkout terms with a durable, purpose-specific key."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path


def seal_quote(payment: dict, state_file: Path, *, create_key: bool = True) -> str:
    # Keep this beside the persisted quotes and include it in the same backup.
    # Login-key rotation must never invalidate an already paid price quote.
    path = Path(state_file).with_name("checkout_quote.key")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        if not create_key:
            raise RuntimeError("Checkout quote key is missing; restore its backup before confirming payments")
        if Path(state_file).exists():
            try:
                pending = json.loads(Path(state_file).read_text(encoding="utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise RuntimeError("Cannot establish whether existing quotes need their original key") from exc
            if not isinstance(pending, dict) or any(
                not isinstance(quote, dict) or "quote_seal" in quote or "quote_version" in quote
                for quote in pending.values()
            ):
                raise RuntimeError("Existing quotes require their original key; restore its backup")
        fd, temporary = tempfile.mkstemp(prefix=".checkout-key-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(os.urandom(32))
                handle.flush()
                os.fsync(handle.fileno())
            with suppress(FileExistsError):  # Another worker may publish its complete key first.
                os.link(temporary, path)
        finally:
            os.unlink(temporary)
    key = path.read_bytes()
    if len(key) != 32:
        raise RuntimeError("Checkout quote key is invalid; restore its backup before confirming payments")
    fields = ("payment_id", "customer_id", "product_id", "amount", "currency",
              "chain", "wallet_address", "created_at", "expires_at", "site")
    body = json.dumps({name: payment.get(name) for name in fields}, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, b"checkout-quote/v1\0" + body, hashlib.sha256).hexdigest()
