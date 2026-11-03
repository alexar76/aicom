"""Bridge failure modes, named so callers can fail closed on the right one.

Every one of these means "do not credit, do not submit". They are distinct types rather
than one error because the CALLER's honest answer differs: a configuration gap is the
operator's to fix, an unreachable chain is transient, and a rejected signature is the
buyer's. Collapsing them would force the request path to guess which it was.
"""

from __future__ import annotations


class BridgeError(RuntimeError):
    """Base for every bridge failure. Never raised directly."""


class BridgeDisabled(BridgeError):
    """The bridge is off. Reaching a bridge-only path with it off is a wiring bug."""


class BridgeConfigError(BridgeError):
    """Something the operator must set is missing or self-contradictory."""


class ChainUnavailable(BridgeError):
    """The chain could not be read. Transient, and never grounds for crediting anyway."""


class ChannelNotOnChain(BridgeError):
    """No escrow channel exists for that id (the contract returns a zero depositor)."""


class EscrowStateRejected(BridgeError):
    """The on-chain channel exists but does not back the credit being asked for."""


class AuthorizationRejected(BridgeError):
    """The buyer's DebitAuthorization does not authorise the debit being recorded."""


class SubmissionRefused(BridgeError):
    """A submission was refused BEFORE any transaction was built or sent.

    Distinct from a failed submission: nothing left this process, so the caller's
    pending record is untouched and safe to retry once the operator fixes the cause.
    """
