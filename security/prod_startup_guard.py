"""
Production startup guard — refuse known weak credentials when ``AIFACTORY_PROD=1``.

Demo hosts (magic-ai-factory.com) should use ``AIFACTORY_DEMO_READONLY=1`` without
``AIFACTORY_PROD=1``. Self-hosted production must never ship with ``demo123`` / ``admin123``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from core.logging_utils import log_suppressed
from core.paths import admin_users_path, legacy_admin_path

logger = logging.getLogger(__name__)

KNOWN_INSECURE_PASSWORDS: frozenset[str] = frozenset(
    {"demo123", "admin123", "password", "changeme", "admin", "factory"}
)

# Literal placeholder fragments that must never reach a production payment address.
# Mirrors the request-time recipient validation in web/backend/api/payment.py so a
# default/example value can never silently settle real funds. Compared lowercase.
_PLACEHOLDER_ADDRESS_FRAGMENTS: tuple[str, ...] = (
    "0xyour",
    "your_wallet",
    "yourwallet",
    "set_me",
    "setme",
    "changeme",
    "todo",
    "example",
    "placeholder",
    "0xdead",
    "0xdemo",
)


# Production self-identification markers, mirrored from
# ``web/backend/services/ai_market_protocol/config._is_production_env`` (also used by
# payment.py, sandbox_isolation.py, alien-monitor monitor_auth.py). Kept in sync so the
# startup guard cannot be bypassed by a deployment that sets one convention but not
# ``AIFACTORY_PROD=1``. Self-contained read — no core import dependency.
_PRODUCTION_ENV_TAGS: frozenset[str] = frozenset({"production", "prod", "live"})


def is_production_mode() -> bool:
    if os.environ.get("AIFACTORY_ENV", "").strip().lower() in _PRODUCTION_ENV_TAGS:
        return True
    for key in ("AIFACTORY_PROD", "AIFACTORY_PRODUCTION"):
        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


def _is_placeholder_address(address: str) -> bool:
    """True when ``address`` is empty, the all-zero address, or a known placeholder.

    Guards against shipping the ``payment.py`` defaults (zero address) or copy-paste
    template values (``0xYour...``, ``SET_ME``, ...) into a live deployment.
    """
    addr = (address or "").strip().lower()
    if not addr:
        return True
    # All-zero EVM address (and any leading-zero variant) — never a real recipient.
    hex_body = addr[2:] if addr.startswith("0x") else addr
    if hex_body and set(hex_body) <= {"0"}:
        return True
    return any(fragment in addr for fragment in _PLACEHOLDER_ADDRESS_FRAGMENTS)


def _load_password_hashes() -> list[str]:
    hashes: list[str] = []
    users_path = Path(os.environ.get("ADMIN_USERS_PATH", str(admin_users_path())))
    if users_path.is_file():
        try:
            data = json.loads(users_path.read_text(encoding="utf-8"))
            for u in data.get("users") or []:
                if isinstance(u, dict) and u.get("password_hash"):
                    hashes.append(str(u["password_hash"]))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            log_suppressed(logger, "prod guard users.json", exc_info=exc)
    legacy = legacy_admin_path()
    if legacy.is_file():
        try:
            cfg = json.loads(legacy.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and cfg.get("password_hash"):
                hashes.append(str(cfg["password_hash"]))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            log_suppressed(logger, "prod guard admin.json", exc_info=exc)
    return hashes


def _admin_uses_insecure_password() -> str | None:
    """Return the matched weak password literal, or None.

    Every (weak password, hash) pair is verified without an early return so the
    runtime does not depend on *which* weak password matched — closing the timing
    side channel an attacker could otherwise use to learn the admin password by
    observing how long the startup check runs. The first match is recorded but the
    loop still completes.
    """
    hashes = _load_password_hashes()
    if not hashes:
        return None
    matched: str | None = None
    try:
        from web.backend.core.security import SecurityManager

        sec = SecurityManager()
        for weak in KNOWN_INSECURE_PASSWORDS:
            for h in hashes:
                if sec.verify_password(weak, h) and matched is None:
                    matched = weak
    except Exception as exc:
        logger.warning("prod_startup_guard: could not verify admin password: %s", exc)
    return matched


def production_startup_issues() -> list[str]:
    """Collect blocking issues for production mode (empty = OK)."""
    if not is_production_mode():
        return []

    issues: list[str] = []

    dev_pw = (os.environ.get("AIFACTORY_DEV_BOOTSTRAP_PASSWORD") or "").strip()
    if dev_pw and dev_pw.lower() in KNOWN_INSECURE_PASSWORDS:
        issues.append(
            f"AIFACTORY_DEV_BOOTSTRAP_PASSWORD is a known demo password ({dev_pw!r}). "
            "Unset it or use a unique secret before AIFACTORY_PROD=1."
        )

    if os.environ.get("AIFACTORY_DEMO_READONLY", "").strip() == "1":
        issues.append(
            "AIFACTORY_PROD=1 together with AIFACTORY_DEMO_READONLY=1 is contradictory — "
            "use DEMO_READONLY only on intentional public demo hosts, not production."
        )

    # JWT: refuse ephemeral signing secret in production. An ephemeral key is
    # regenerated on every restart (invalidating sessions) and weakens token
    # integrity guarantees. Set JWT_SECRET_KEY or mount jwt_secret.key instead.
    if (
        os.environ.get("AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL", "").strip().lower()
        in ("1", "true", "yes")
    ):
        issues.append(
            "AIFACTORY_INSECURE_JWT_ALLOW_EPHEMERAL is enabled in production mode — "
            "JWTs would be signed with a throwaway secret regenerated on every restart. "
            "Unset it and provide a persistent JWT_SECRET_KEY (>=32 chars) or "
            "jwt_secret.key before running with AIFACTORY_PROD=1."
        )

    # SSO: trusted-header auth with broad default CIDRs lets any host inside the
    # private network forge the identity header. Require an explicit, narrow allowlist.
    if (os.environ.get("AIFACTORY_SSO_TRUSTED_HEADER") or "").strip():
        cidrs = (os.environ.get("AIFACTORY_SSO_TRUSTED_CIDRS") or "").strip()
        broad = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "0.0.0.0/0")
        if not cidrs or any(b in cidrs for b in broad):
            issues.append(
                "AIFACTORY_SSO_TRUSTED_HEADER is enabled but AIFACTORY_SSO_TRUSTED_CIDRS "
                "is unset or includes a broad private range — any host on the network "
                "could spoof the identity header. Pin it to the reverse-proxy IP "
                "(e.g. 10.0.0.10/32) before running with AIFACTORY_PROD=1."
            )

    weak = _admin_uses_insecure_password()
    if weak:
        issues.append(
            f"Admin account still uses a known weak password ({weak!r}). "
            "Change it via Settings or re-bootstrap before running with AIFACTORY_PROD=1."
        )

    # Master crypto switch (default OFF). The payment interlocks below only matter
    # when crypto is ENABLED — a legitimately crypto-disabled prod host has no
    # payment surface to harden and must be allowed to start without recipients,
    # contracts, or testnet flags. (Self-contained read — no core import dependency.)
    crypto_on = os.environ.get("AIFACTORY_CRYPTO_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
    recipient = (os.environ.get("AIMARKET_PAYMENT_RECIPIENT") or "").strip()
    contract = (os.environ.get("AIFACTORY_AI_MARKET_CONTRACT") or "").strip()

    if crypto_on:
        # Payment: refuse production with stub verification. Anything other than an
        # explicit "0" (including unset → defaults to the insecure "1", and stray
        # truthy spellings like "true"/"yes") must fail closed so a typo cannot leave
        # stub acceptance silently enabled.
        if os.environ.get("AIFACTORY_PAYMENT_VERIFY_STUB", "1").strip() != "0":
            issues.append(
                "AIFACTORY_PAYMENT_VERIFY_STUB must be explicitly '0' in production mode — "
                "otherwise all payment transactions are accepted without on-chain "
                "verification. Set AIFACTORY_PAYMENT_VERIFY_STUB=0 before AIFACTORY_PROD=1."
            )

        # Payment: refuse production without a configured recipient (or a placeholder).
        if not recipient or _is_placeholder_address(recipient):
            issues.append(
                "AIMARKET_PAYMENT_RECIPIENT is not set or is a placeholder/zero address — "
                "real payments have nowhere to settle. Set a valid wallet address before "
                "running with AIFACTORY_PROD=1."
            )

        # Payment: refuse production testnet mode. As above, require an explicit "0";
        # testnet mode accepts demo/synthetic transaction hashes as if they settled.
        if os.environ.get("AIFACTORY_PAYMENT_TESTNET", "1").strip() != "0":
            issues.append(
                "AIFACTORY_PAYMENT_TESTNET must be explicitly '0' in production mode — "
                "testnet mode accepts demo transaction hashes against a testnet RPC. "
                "Set AIFACTORY_PAYMENT_TESTNET=0 before running with AIFACTORY_PROD=1."
            )

        # Payment: the on-chain settlement contract must be a real, non-placeholder
        # address — config.pilot_tuple() reads AIFACTORY_AI_MARKET_CONTRACT and an empty
        # or stub value would point on-chain verification at nothing.
        if not contract or _is_placeholder_address(contract):
            issues.append(
                "AIFACTORY_AI_MARKET_CONTRACT is not set or is a placeholder/zero address — "
                "on-chain payment verification has no contract to query. Set the deployed "
                "AIMarket contract address before running with AIFACTORY_PROD=1."
            )
    else:
        # Inverse fail-closed: payment addresses are configured but crypto is OFF, so
        # nothing would ever settle. Surface it so an operator who meant to accept
        # payments can't silently collect nothing (and one who meant crypto off can
        # remove the stale addresses).
        if (recipient and not _is_placeholder_address(recipient)) or (
            contract and not _is_placeholder_address(contract)
        ):
            issues.append(
                "Payment addresses are configured (AIMARKET_PAYMENT_RECIPIENT / "
                "AIFACTORY_AI_MARKET_CONTRACT) but AIFACTORY_CRYPTO_ENABLED is off — "
                "no payment can settle. Set AIFACTORY_CRYPTO_ENABLED=1 to accept payments, "
                "or unset the addresses to confirm crypto is intentionally disabled."
            )

    # ZK: refuse simulated ZK in production (privacy-preserving claims are void)
    if os.environ.get("AIMARKET_ZK_SIMULATED", "1").strip() == "1":
        issues.append(
            "AIMARKET_ZK_SIMULATED=1 in production mode — ZK proofs are simulated "
            "(no cryptographic privacy). Set AIMARKET_ZK_SIMULATED=0 and deploy "
            "real Groth16 circuits before running with AIFACTORY_PROD=1."
        )

    # DinD sandbox: refuse production when sandbox containers run on the local
    # Docker daemon (privileged or socket-mount). Require an explicit external host.
    if os.environ.get("AIFACTORY_SANDBOX_REQUIRE_CONTAINER", "").strip() == "1":
        docker_host = (os.environ.get("DOCKER_HOST") or "").strip()
        if not docker_host or docker_host.startswith("unix://"):
            issues.append(
                "AIFACTORY_SANDBOX_REQUIRE_CONTAINER=1 in production mode without "
                "DOCKER_HOST pointing to an external Docker daemon — sandbox "
                "containers would run on the host kernel (privileged or socket "
                "mount). Set DOCKER_HOST=tcp://<remote>:2375 (TLS-secured) before "
                "running with AIFACTORY_PROD=1."
            )

    # Docker socket: refuse production when the host Docker socket is mounted into
    # the app container (AIFACTORY_USE_HOST_DOCKER=1). /var/run/docker.sock is a
    # direct host-root escape vector — use the DinD sidecar (docker-compose.dind.yml).
    if os.environ.get("AIFACTORY_USE_HOST_DOCKER", "").strip() == "1":
        issues.append(
            "AIFACTORY_USE_HOST_DOCKER=1 in production mode mounts /var/run/docker.sock "
            "into the app container — a direct host-root escape vector. Use the default "
            "DinD sidecar (docker-compose.dind.yml) before running with AIFACTORY_PROD=1."
        )

    # Database: SQLite is dev/demo only — Postgres required for production load.
    sqlite_flag = os.environ.get("USE_SQLITE", "").strip().lower()
    pipeline_db = os.environ.get("PIPELINE_DB_BACKEND", "sqlite").strip().lower()
    if sqlite_flag in ("1", "true", "yes") or pipeline_db == "sqlite":
        issues.append(
            "SQLite pipeline backend in production mode (USE_SQLITE or "
            "PIPELINE_DB_BACKEND=sqlite). Use Postgres for production — see "
            "docs/architecture/scaling.md and set PIPELINE_DB_BACKEND=postgres."
        )

    # LLM: at least one enabled provider must have a resolvable API key.
    try:
        from llm.startup_validation import production_llm_key_issues

        issues.extend(production_llm_key_issues())
    except Exception as exc:
        logger.warning("prod_startup_guard: LLM key validation skipped: %s", exc)

    # ZK: groth16 artifacts must exist when AIMARKET_ZK_BACKEND=groth16.
    try:
        from security.zk_artifacts import production_zk_issues

        issues.extend(production_zk_issues())
    except Exception as exc:
        logger.warning("prod_startup_guard: ZK artifact validation skipped: %s", exc)

    # Mandatory admin 2FA when AIFACTORY_REQUIRE_ADMIN_2FA=1.
    if os.environ.get("AIFACTORY_REQUIRE_ADMIN_2FA", "").strip().lower() in ("1", "true", "yes"):
        issues.extend(_production_2fa_issues())

    return issues


def _production_2fa_issues() -> list[str]:
    """Require TOTP or WebAuthn on the primary admin account."""
    from security import webauthn_admin as wa

    issues: list[str] = []
    cfg_path = legacy_admin_path()
    if not cfg_path.is_file():
        issues.append(
            "AIFACTORY_REQUIRE_ADMIN_2FA=1 but admin.json is missing — "
            "bootstrap admin and enable TOTP or WebAuthn."
        )
        return issues
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append("Cannot read admin.json for 2FA requirement check.")
        return issues
    totp_on = bool(cfg.get("totp_enabled") and cfg.get("totp_secret"))
    webauthn_on = wa.webauthn_is_enabled(cfg if isinstance(cfg, dict) else {})
    if not totp_on and not webauthn_on:
        issues.append(
            "AIFACTORY_REQUIRE_ADMIN_2FA=1 but neither TOTP nor WebAuthn is enabled "
            "for the primary admin. Enable 2FA in Admin → Settings before production."
        )
    return issues


def assert_production_startup_safe(*, exit_on_failure: bool = True) -> None:
    issues = production_startup_issues()
    if not issues:
        return
    msg = "Production startup refused:\n  - " + "\n  - ".join(issues)
    logger.error(msg)
    if exit_on_failure:
        print(msg, file=sys.stderr)
        raise SystemExit(1)
    raise RuntimeError(msg)
