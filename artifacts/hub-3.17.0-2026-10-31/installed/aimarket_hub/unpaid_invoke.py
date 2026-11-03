"""The unpaid-invoke gate MOMUS probes (``unpaid_invoke_refused``).

Kept as its own module so Factory remediation can author a patch without opening
``aimarket-hub/aimarket_hub/api.py`` (that file is larger than the scratch-tree cap).
``api.invoke`` calls this *before* the provider runs: a priced capability with an
active payment rail and no channel / credits / x402 must 402, not 200+output.
"""

from __future__ import annotations

from typing import Any


def must_refuse_unpaid_paid_capability(
    *,
    price_usd: float,
    sandbox_mode: bool,
    price_rail_active: bool,
    payment_channel: str | None,
    credit_account: str,
    x402_accepted: dict[str, Any] | None,
) -> bool:
    """True when this invoke must 402 before the provider runs.

    Sandbox visitors and unpriced capabilities stay free. When no rail is on
    (crypto off, credits off, no x402 header) the hub still serves the catalogue
    unpaid — that default is deliberate and tested. The finding MOMUS exists to
    catch is a *priced* call on a hub that *does* have a rail, served anyway.
    """
    if sandbox_mode:
        return False
    if float(price_usd or 0) <= 0:
        return False
    if not price_rail_active:
        return False
    if (payment_channel or "").strip():
        return False
    if (credit_account or "").strip():
        return False
    if x402_accepted is not None:
        return False
    return True
