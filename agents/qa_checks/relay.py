"""Relay products: session token salts, UUID primary-key lookups and pinned compatibility
fragments.
"""

from __future__ import annotations

import re
from pathlib import Path


class RelayChecksMixin:
    """Relay checks: token salt, UUID key lookup, pinned compatibility."""

    def _assess_session_token_salt(self, product_id: str, code_files: list[dict]) -> list[dict]:
        """Login must sign with the same salt/secret the protected routes verify.

        Measured on Factory Relay: UI login 200 with salt=relay-access-token, then
        GET /api/handoffs 401 because verify uses relay-session. Vercel publish used
        to patch only the bundle copy. This finding is measured (API contract:) so
        an LLM cannot drop it.
        """
        issues: list[dict] = []
        login_salt = False
        protected_salt = False
        cookie_session = False
        cookie_relay = False
        auth_file = f"code/{product_id}"
        for info in code_files:
            path = str(info.get("path") or "").replace("\\", "/")
            content = str(info.get("content") or "")
            name = Path(path).name
            if name == "auth.py" and "relay-access-token" in content:
                login_salt = True
                auth_file = path
            if name in {"handoffs.py", "security.py"} and "relay-session" in content:
                protected_salt = True
            if name == "auth.py" and re.search(r'key=["\']session["\']', content):
                cookie_session = True
            if name == "deps.py" and "SESSION_COOKIE_NAME" in content and "relay_session" in content:
                cookie_relay = True
        if login_salt and protected_salt:
            issues.append(
                {
                    "severity": "high",
                    "title": "API contract: login token salt does not match protected routes",
                    "description": (
                        "Login signs with salt=relay-access-token while handoffs/security verify "
                        "relay-session. The visitor sees a successful login; business routes return "
                        "401. Factory must rewrite login to create_session_token (session_secret + "
                        "relay-session) in data/code — not only the Vercel bundle."
                    ),
                    "file": auth_file,
                }
            )
        if cookie_session and cookie_relay:
            issues.append(
                {
                    "severity": "high",
                    "title": "API contract: login cookie name does not match session reader",
                    "description": (
                        "Login Set-Cookie uses key=session but deps SESSION_COOKIE_NAME is "
                        "relay_session. Align the cookie name in data/code."
                    ),
                    "file": auth_file,
                }
            )
        return issues

    def _assess_uuid_pk_lookup(self, product_id: str, code_files: list[dict]) -> list[dict]:
        """Token ``sub`` / path ids are str; SQLAlchemy UUID columns need uuid.UUID.

        Measured on Factory Relay: login 200, then GET /api/handoffs 500 because
        ``Operator.id == operator_id`` passes a string into a UUID column. Prefix
        ``API contract:`` so an LLM cannot drop it.
        """
        issues: list[dict] = []
        hit_file = f"code/{product_id}"
        raw = False
        for info in code_files:
            path = str(info.get("path") or "").replace("\\", "/")
            if not path.endswith(".py"):
                continue
            content = str(info.get("content") or "")
            if re.search(
                r"\b(?:Operator|Handoff)\.id\s*==\s*(?:operator_id|handoff_id)\b",
                content,
            ):
                raw = True
                hit_file = path
                break
        if raw:
            issues.append(
                {
                    "severity": "high",
                    "title": "API contract: string UUID compared to UUID column",
                    "description": (
                        "verify_access_token succeeds, then Operator.id == operator_id "
                        "(or Handoff.id == handoff_id) raises because the token/path id is "
                        "str and the SQLAlchemy column is UUID. Factory must coerce with "
                        "uuid.UUID(str(...)) in data/code — not only a Docker sed."
                    ),
                    "file": hit_file,
                }
            )
        return issues

    def _assess_relay_pinned_compat(self, product_id: str, code_files: list[dict]) -> list[dict]:
        """Enum `.value` and raw UUID JSON must be coerced — not only in an AEGIS Docker pin.

        Measured on Factory Relay: receipt/audit dump ``handoff.id`` / ``e.action.value``
        and ORM models hit Pydantic UUID columns → 500. Prefix ``API contract:``.
        """
        from web.backend.services.vercel_fullstack_adapter import _RELAY_PINNED_FRAGMENTS

        issues: list[dict] = []

        def _file_for_rel(rel: str) -> dict | None:
            needle = rel.replace("\\", "/")
            for info in code_files:
                path = str(info.get("path") or "").replace("\\", "/")
                if path.endswith(needle) or path.endswith("/" + needle):
                    return info
            return None

        hit_file = f"code/{product_id}"
        raw = False
        for rel, old, new in _RELAY_PINNED_FRAGMENTS:
            info = _file_for_rel(rel)
            if not info:
                continue
            content = str(info.get("content") or "")
            if old in content and new not in content:
                raw = True
                hit_file = str(info.get("path") or hit_file)
                break
        if raw:
            issues.append(
                {
                    "severity": "high",
                    "title": "API contract: Relay enum/ORM fragment not coerced",
                    "description": (
                        "Receipt/audit/handoff_service dump Enum.value or UUID objects, or "
                        "Pydantic ORM models lack UUID stringify. Factory must apply the "
                        "pinned exact fragments in data/code — not an AEGIS Docker sed."
                    ),
                    "file": hit_file,
                }
            )
            return issues
        has_handoffs = _file_for_rel("routers/handoffs.py") is not None
        has_receipt = _file_for_rel("services/receipt.py") is not None
        if has_handoffs and has_receipt:
            for rel, old, new in _RELAY_PINNED_FRAGMENTS:
                info = _file_for_rel(rel)
                if info is None:
                    issues.append(
                        {
                            "severity": "high",
                            "title": "API contract: Relay pinned fragment file missing",
                            "description": (
                                f"Expected {rel} for the pinned Relay heal; structure changed "
                                "so the factory will not guess a neighbour."
                            ),
                            "file": f"code/{product_id}/{rel}",
                        }
                    )
                    break
                content = str(info.get("content") or "")
                if old not in content and new not in content:
                    issues.append(
                        {
                            "severity": "high",
                            "title": "API contract: Relay pinned fragment moved",
                            "description": (
                                f"{rel} no longer contains the pinned bytes; fail-fast rather "
                                "than patching the wrong site. Factory must not guess."
                            ),
                            "file": str(info.get("path") or rel),
                        }
                    )
                    break
        return issues
