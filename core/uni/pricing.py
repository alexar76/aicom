"""USD ↔ UNI conversion — fixed peg, integer UNI."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from core.uni.config import uni_topup_spread_bps, uni_usd_cents_per_uni
from core.uni.constants import UNI_PER_USDT


def usd_to_uni(usd: float, *, apply_spread: bool = False) -> int:
    """
    Convert USD to whole UNI at fixed peg (default 100 UNI per $1).

    ``apply_spread=True`` applies top-up fee (e.g. 0% for psy-friendly onboarding).
    """
    if usd <= 0:
        return 0
    uni = (Decimal(str(usd)) * Decimal(100) * Decimal(uni_usd_cents_per_uni())).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if apply_spread and uni > 0:
        spread = Decimal(uni_topup_spread_bps()) / Decimal(10_000)
        uni = (uni * (Decimal(1) - spread)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(uni)


def uni_to_usd(uni: int | float) -> float:
    """USD equivalent at fixed peg."""
    denom = 100.0 * uni_usd_cents_per_uni()
    if denom <= 0:
        return 0.0
    return round(float(uni) / denom, 6)


def platform_fee_uni(gross_uni: int, *, fee_bps: int | None = None) -> int:
    from core.uni.config import uni_platform_fee_bps

    bps = fee_bps if fee_bps is not None else uni_platform_fee_bps()
    if gross_uni <= 0 or bps <= 0:
        return 0
    return gross_uni * bps // 10_000


def withdraw_net_usd(gross_uni: int, *, fee_bps: int | None = None) -> float:
    from core.uni.config import uni_withdraw_fee_bps

    bps = fee_bps if fee_bps is not None else uni_withdraw_fee_bps()
    gross_usd = uni_to_usd(gross_uni)
    return round(gross_usd * max(0.0, 1.0 - bps / 10_000.0), 6)
