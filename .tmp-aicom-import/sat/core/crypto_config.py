"""Ecosystem-wide master switch for crypto / blockchain / on-chain payments.

A real blockchain is **not** required to run any AICOM component. Crypto is
**OFF by default** across the whole ecosystem: with the switch off, nothing
loads a wallet, contacts a chain/RPC, opens a payment channel, returns a 402
``Payment Required``, verifies a transaction on-chain, or settles UNI/lottery.
Every component still runs — capabilities are served on a free tier, federation
signing and internal accounting keep working — it just never touches money.

Enabling crypto is a single deployment-wide opt-in: set one env var and every
process (Python and the ARGUS/Node client, which read the same name) turns the
economy on. Even then each component still needs its own proper config
(recipient addresses, RPC endpoints, wallet keys) and, in production, the
existing ``AIFACTORY_PROD`` interlocks.

This module is the single source of truth for the Python monorepo
(web/backend, core, orchestrator). Standalone packages (aimarket-hub, oracles,
ai-service-mesh, lottery, ARGUS) read the *same* env var with the *same*
default-off, *same* truthy rule — the contract is shared even though the helper
is duplicated where there is no import boundary.
"""

from __future__ import annotations

import os

#: The master env var. Default OFF. Truthy values: 1, true, yes, on.
ENV_VAR = "AIFACTORY_CRYPTO_ENABLED"

_TRUTHY = {"1", "true", "yes", "on"}


def crypto_enabled() -> bool:
    """Return True only if the ecosystem crypto switch is explicitly enabled.

    Unset, empty, ``0``/``false``/``no``/``off`` (anything not truthy) → disabled.
    """
    return os.environ.get(ENV_VAR, "0").strip().lower() in _TRUTHY


def require_crypto(what: str = "this operation") -> None:
    """Raise if crypto is disabled — for code paths that must not run when off."""
    if not crypto_enabled():
        raise RuntimeError(
            f"{what} requires crypto, which is disabled. "
            f"Set {ENV_VAR}=1 to enable the on-chain economy."
        )


def crypto_status_line() -> str:
    """One-line human-readable status, handy for startup banners / health."""
    return (
        "crypto ENABLED (wallet/chain/payments on)"
        if crypto_enabled()
        else f"crypto OFF (default) — no blockchain required; set {ENV_VAR}=1 to enable"
    )
