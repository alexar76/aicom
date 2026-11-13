"""Fund the dedicated owner-only CMC test wallet with two 0.01 USDC calls."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publisher-worker-and-debian-2026-11-13"))
import fund_worker

fund_worker.AMOUNT = 20_000
fund_worker.PAYOUT_SENDER = "0x1cdb27372Ed3d5d37080A5A3256512b17EA321bc"
fund_worker.main()
