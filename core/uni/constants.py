"""UNI economic constants — fixed peg and fee schedule."""

from __future__ import annotations

# 1 UNI = $0.01 USDT (100 UNI per $1 USDT). Not a tradable token — internal store credit.
UNI_PER_USDT: int = 100

PLATFORM_OWNER_ID: str = "PLATFORM_FEES"
PLATFORM_OWNER_TYPE: str = "platform"

# Basis points (1 bps = 0.01%)
DEFAULT_TOPUP_FEE_BPS: int = 0
DEFAULT_PLATFORM_FEE_BPS: int = 500  # 5% per invoke / hold charge
DEFAULT_WITHDRAW_FEE_BPS: int = 100  # 1% on withdrawal
DEFAULT_MIN_WITHDRAW_UNI: int = 2000  # $20 at fixed peg

# Treasury health alert when on-chain USDT / required < this ratio
TREASURY_HEALTHY_RATIO: float = 0.999
