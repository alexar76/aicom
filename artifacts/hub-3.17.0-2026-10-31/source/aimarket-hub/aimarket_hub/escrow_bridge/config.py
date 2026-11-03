"""Escrow bridge settings — every read dynamic, every default inert.

The bridge is the only part of the hub that can cause value to move on-chain, so its
configuration is deliberately boring and its defaults are deliberately useless:

    mode OFF                → nothing in the request path changes at all
    strategy "plan"         → the mirror builds and SIMULATES calldata, submits nothing
    no keys anywhere        → a signing key is read from the environment or never seen

Reads go through the functions below (not module constants) so tests and operators can
change one knob without reimporting the hub — the same convention channels.py and
verified_settlement.py already use for their prod gates.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

# A non-plan strategy can broadcast a transaction, so it takes a second, deliberate act
# beyond naming the strategy: the operator must type this phrase. It is not a secret —
# it exists so "I set a strategy while exploring" cannot silently become "I authorised
# spending from the hub's key".
SUBMIT_CONFIRM_PHRASE = "i-understand-this-moves-funds"

STRATEGY_PLAN = "plan"
STRATEGY_EXTERNAL = "external"
STRATEGY_ENV = "env"
_STRATEGIES = (STRATEGY_PLAN, STRATEGY_EXTERNAL, STRATEGY_ENV)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name, default) or "").strip()


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    """Master switch. OFF by default: an operator who has not opted in gets today's hub."""
    return _truthy(_env("AIMARKET_ESCROW_BRIDGE_ENABLED", "0"))


def required() -> bool:
    """Make the CUSTODIAL deposit path unreachable.

    The bridge being `enabled()` only makes escrow funding *available*: a client may
    still open a channel by transferring to the operator's settlement wallet, and that
    branch cannot be switched off. So a hub that advertises AIMarketEscrow's
    non-custodial guarantees is describing a path its own default does not take, and
    channel balances remain an operator liability (KI-11, consequence 1).

    With this on, `/channel/open` accepts ONLY an `escrow_channel_id` the contract
    itself confirms. It is refused outright unless the bridge is enabled, because
    "required" without "available" is a hub that cannot open a channel at all and
    would say so one confusing error at a time.
    """
    return _truthy(_env("AIMARKET_ESCROW_REQUIRED", "0"))


def network_id() -> str:
    """Chain the escrow lives on. Empty → chain_net's active network."""
    return _env("AIMARKET_ESCROW_NETWORK")


def contract_address() -> str:
    """Escrow address override. Empty → the address chain_net resolved for the network."""
    return _env("AIMARKET_ESCROW_CONTRACT")


def hub_address() -> str:
    """This hub's EVM address — the ``hub`` field bound into every DebitAuthorization.

    Required in escrow mode and NOT defaulted: the contract binds the signature to one
    hub, so a wrong value here produces authorizations that no contract will accept.
    Guessing it would turn a configuration mistake into a silent, chain-side failure
    discovered only when money should have moved.
    """
    return _env("AIMARKET_ESCROW_HUB_ADDRESS")


def submit_strategy() -> str:
    """``plan`` (default, submits nothing) | ``external`` (operator signer) | ``env`` (key).

    An unrecognised value falls back to ``plan`` rather than raising: a typo in a
    deployment variable must not be able to escalate what the mirror is allowed to do,
    and it must not take the hub down either.
    """
    raw = _env("AIMARKET_ESCROW_SUBMIT_STRATEGY", STRATEGY_PLAN).lower()
    return raw if raw in _STRATEGIES else STRATEGY_PLAN


def submit_confirmed() -> bool:
    """Whether the operator typed the confirmation phrase for a value-moving strategy."""
    return _env("AIMARKET_ESCROW_SUBMIT_CONFIRM") == SUBMIT_CONFIRM_PHRASE


def signer_url() -> str:
    """External signer endpoint (``external`` strategy). No key enters this process."""
    return _env("AIMARKET_ESCROW_SIGNER_URL")


def signer_token() -> str:
    """Bearer token for the external signer, if it requires one."""
    return _env("AIMARKET_ESCROW_SIGNER_TOKEN")


def private_key() -> str:
    """Hub signing key for the ``env`` strategy. Read here and nowhere else.

    Never logged, never persisted, never included in an error message — the store and
    the mirror only ever see the transaction they asked to have signed.
    """
    return _env("AIMARKET_ESCROW_PRIVATE_KEY")


def db_path() -> str:
    """The bridge's own SQLite file. Empty → beside the channel ledger's database."""
    return _env("AIMARKET_ESCROW_BRIDGE_DB_PATH")


def rpc_timeout_s() -> float:
    try:
        return max(1.0, float(_env("AIMARKET_ESCROW_RPC_TIMEOUT_S", "10") or 10))
    except ValueError:
        return 10.0


def max_authorization_ttl_s() -> int:
    """Upper bound on how far in the future a DebitAuthorization deadline may sit.

    A deadline is the buyer's protection: it caps how long the hub may hold a signed
    claim on their money. An unbounded deadline turns one signature into a standing
    licence, so an authorization asking for more than this is refused.
    """
    try:
        return max(60, int(float(_env("AIMARKET_ESCROW_AUTH_MAX_TTL_S", "86400") or 86400)))
    except ValueError:
        return 86400


def expiry_margin_s() -> int:
    """How long before the channel's on-chain ``expiresAt`` the hub stops serving on it.

    A debit only lands while the contract still accepts it (``block.timestamp <=
    expiresAt``), and the sweep that submits debits runs every 15 minutes. Serving a call
    closer to expiry than one sweep can reach means serving it for free: the debit
    reverts, and ``expireChannel`` hands the whole balance back to the depositor.
    """
    try:
        return max(0, int(float(_env("AIMARKET_ESCROW_EXPIRY_MARGIN_S", "1800") or 1800)))
    except ValueError:
        return 1800


def _usd_cap(name: str, default: str) -> float:
    """A non-negative USD ceiling from the environment. 0 means "no limit".

    "inf" (or any non-finite value) also means no limit: read literally it reached
    usd_to_base_units, which refuses it, and every capped call failed with an error about a
    deposit amount."""
    try:
        value = float(_env(name, default) or default)
    except ValueError:
        value = float(default)
    if not math.isfinite(value):
        return 0.0
    return max(0.0, value)


def min_authorization_ttl_s() -> int:
    """How far ahead a debit authorization's deadline must be when the hub accepts it.

    The deadline is the buyer's to choose, and the contract refuses a debit after it. One
    signed seconds ahead was verified, served, and then abandoned by the 15-minute sweep as
    expired — every such call free. Half an hour is two sweeps; our clients sign an hour.
    """
    try:
        return max(0, int(float(_env("AIMARKET_ESCROW_AUTH_MIN_TTL_S", "1800") or 1800)))
    except ValueError:
        return 1800


def max_uncollected_usd() -> float:
    """Ceiling on what the hub serves on credit on one escrow channel. 0 disables it.

    Every call in a nonce window is collected by ONE debit, and until that debit lands
    the live V1 contract lets the depositor settle or refund and take back the whole
    balance — every call served since the last landed debit included. The sweep runs
    every 15 minutes under pass and day caps, so that window is real. Capping the running
    total per channel bounds what one channel can take that way to this amount; the
    first call of a window is always served, whatever its price.
    """
    return _usd_cap("AIMARKET_ESCROW_MAX_UNCOLLECTED_USD", "5.0")


def max_usd_per_pass() -> float:
    """Ceiling on the total USD one mirror pass may collect. 0 disables the cap.

    KI-11 required a "bounded" hot wallet and there was no bound of any kind: a single
    pass would submit every unresolved authorization it could, so a bug in the ledger, a
    tampered store, or simply a long unattended backlog all had the same unlimited blast
    radius. A pass ceiling is the cheap half of the bound — it does not stop a determined
    attacker with the key, but it stops the hub from acting on a mistake at full speed,
    and an operator who sees a pass stop at the cap learns something is wrong while the
    amount is still small.

    Deliberately a per-PASS cap and not a per-row one: the risk scales with what a single
    unattended run can move, not with any individual debit.
    """
    return _usd_cap("AIMARKET_ESCROW_MAX_USD_PER_PASS", "5.0")


def max_usd_per_day() -> float:
    """Ceiling on USD collected in a rolling 24h, across passes. 0 disables the cap.

    The per-pass cap alone is defeated by running passes back to back — which is exactly
    what an unattended timer does. This one is measured from the store's own record of what
    was submitted or confirmed, so it survives a process restart.
    """
    return _usd_cap("AIMARKET_ESCROW_MAX_USD_PER_DAY", "25.0")


@dataclass(frozen=True)
class SubmitPolicy:
    """Resolved answer to "may this process broadcast, and how?"."""

    strategy: str
    confirmed: bool
    reason: str = ""

    @property
    def may_broadcast(self) -> bool:
        return self.strategy != STRATEGY_PLAN and self.confirmed and not self.reason


def submit_policy() -> SubmitPolicy:
    """Resolve the submission policy, refusing anything under-configured.

    Every path that could broadcast has to come through here, so the "can this move
    money" decision exists in exactly one place and reads the same in tests as in prod.
    """
    strategy = submit_strategy()
    if strategy == STRATEGY_PLAN:
        return SubmitPolicy(strategy=strategy, confirmed=False)
    if not submit_confirmed():
        return SubmitPolicy(
            strategy=strategy, confirmed=False,
            reason=(
                f"strategy {strategy!r} can broadcast — set "
                f"AIMARKET_ESCROW_SUBMIT_CONFIRM={SUBMIT_CONFIRM_PHRASE!r} to allow it"
            ),
        )
    if strategy == STRATEGY_EXTERNAL and not signer_url():
        return SubmitPolicy(
            strategy=strategy, confirmed=True,
            reason="strategy 'external' needs AIMARKET_ESCROW_SIGNER_URL",
        )
    if strategy == STRATEGY_ENV and not private_key():
        return SubmitPolicy(
            strategy=strategy, confirmed=True,
            reason="strategy 'env' needs AIMARKET_ESCROW_PRIVATE_KEY",
        )
    return SubmitPolicy(strategy=strategy, confirmed=True)


def describe() -> dict[str, object]:
    """Operator-facing snapshot. Deliberately reports NO secret material."""
    policy = submit_policy()
    return {
        "enabled": enabled(),
        "required": required(),
        "custodial_deposit_reachable": not required(),
        "network": network_id() or "(chain_net active)",
        "contract": contract_address() or "(chain_net registry)",
        "hub_address_set": bool(hub_address()),
        "strategy": policy.strategy,
        "may_broadcast": policy.may_broadcast,
        "blocked_reason": policy.reason,
        "signer_url_set": bool(signer_url()),
        "private_key_set": bool(private_key()),
        "max_usd_per_pass": max_usd_per_pass() or None,
        "max_usd_per_day": max_usd_per_day() or None,
    }
