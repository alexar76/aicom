"""Settings for the stall-row x402 service (one deployment, 25 paid routes)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("stall-row.config")

BASE_MAINNET = "eip155:8453"
SOLANA_MAINNET = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"

# His payout wallet on Base (EVM) — the same payTo Token Verdict,
# RouteVerdict and ListSmith use. Overridable via X402_PAY_TO.
OWNER_WALLET = "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F"
PLACEHOLDER_WALLETS = {"0x0000000000000000000000000000000000000000"}

# His Solana wallet (Phantom; receiving only — the service never holds a
# Solana key and never signs; the facilitator settles SPL transfers to
# this address). This is the same Solana payTo Token Verdict's live rail
# advertises. Overridable via X402_SOLANA_PAY_TO.
SOLANA_OWNER_WALLET = "FeyyAfoCbn1psQ6x8gxN8YQbXZVpTSibZwP6mkXckXUJ"
# USDC mint on Solana mainnet (Circle SPL USDC, 6 decimals).
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# The only routes on the row that also accept Solana USDC: the two
# Fleet Check routes. They gain a second accept, not a sibling route —
# the priced route count does not move.
SOLANA_ACCEPT_PATHS = frozenset({"/v1/fleet-check", "/v1/fleet-check/pack"})

# ultravioletadao public x402 facilitator (no keys). Verified via /supported:
# serves eip155:8453 (Base) with the exact scheme.
FACILITATOR_URL = "https://facilitator.ultravioletadao.xyz"

# PayAI public x402 facilitator (no keys for the exact scheme). Settling
# through it catalogs these routes in the PayAI index — each facilitator's
# catalog indexes only its own settlements.
PAYAI_FACILITATOR_URL = "https://facilitator.payai.network"

# Public Base JSON-RPC (base.org). Overridable for a keyed/private RPC.
BASE_RPC_URL = "https://mainnet.base.org"

# Blockscout's Base instance. NOTE: from some networks (incl. the build
# sandbox) base.blockscout.com intermittently answers with a Cloudflare
# challenge page instead of JSON. Every Blockscout-backed field degrades
# to "unknown"/omitted when that happens — see app/blockscout.py.
BLOCKSCOUT_BASE_URL = "https://base.blockscout.com"

CDP_DISCOVERY_RESOURCES_URL = (
    "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
)

# Route prices in USDC smallest units (6 decimals) — the single source of
# truth; discovery.py renders the "$x.xx" strings from these.
PRICE_UNITS: dict[str, int] = {
    "/v1/wallet-snapshot": 5_000,      # $0.005
    "/v1/allowance-audit": 5_000,      # $0.005
    "/v1/tx-decoder": 2_000,           # $0.002
    "/v1/gas-oracle": 1_000,           # $0.001
    "/v1/wallet-verdict": 20_000,      # $0.02
    "/v1/pre-trade-guard": 5_000,      # $0.005 — Pre-Trade Guard: screen a payTo before paying it
    "/v1/tube-search": 10_000,         # $0.01
    "/v1/page-to-markdown": 10_000,    # $0.01
    "/v1/repo-vitals": 5_000,          # $0.005
    "/v1/price-check": 50_000,        # $0.05
    "/v1/card-smith": 100_000,         # $0.10
    "/v1/job-scout": 50_000,           # $0.05
    "/v1/recheck": 5_000,              # $0.005
    "/v1/index/changes": 100_000,      # $0.10 — Verdict Index catalog changelog diff
    "/v1/orchestrate": 750_000,        # $0.75 — one combined fleet report (4 legs)
    "/v1/counterparty-report": 1_000_000,  # $1.00 — one bundled report on one seller
    "/v1/grade-my-stall": 5_000,       # $0.005 — one seller report card (probe tier)
    "/v1/receipt-verify": 2_000,       # $0.002 — one verified on-chain receipt (probe tier)
    "/v1/flagged-paytos": 5_000,       # $0.005 — the bad-payTo registry feed (probe tier)
    "/v1/agent-card-verify": 5_000,    # $0.005 — one ERC-8004 agent-card verification (probe tier)
    "/v1/recheck/pack": 1_000_000,     # $1.00 — 250 prepaid rechecks on one endpoint
    "/v1/fleet-check": 100_000,        # $0.10 — one whole-fleet health sweep (unpaid probes)
    "/v1/fleet-check/pack": 5_000_000,  # $5.00 — 100 prepaid fleet sweeps of one fixed fleet definition
    "/v1/fleet-pass": 5_000_000,       # $5.00 — prepaid USD balance for all fleet routes
    "/v1/fleet-pass-20": 20_000_000,   # $20.00 — Fleet Pass v2: framework working pass, same ledger/TTL
}


# --- recheck store location --------------------------------------------------
#
# Where the watch/pack sqlite lives decides whether sold pack balances
# survive a redeploy. Resolution order:
#   1. STALLROW_RECHECK_DB set -> that exact path wins.
#   2. A volume mounted at /data (Railway Volume) -> /data/recheck.db.
#   3. Plain "recheck.db" on the service's own (ephemeral) disk.
# Durability is measured, never assumed from the path string: a path is
# persistent only when its nearest existing ancestor directory is a
# mount point. The probes are bound at module level so tests can fake
# a volume mount without one.

VOLUME_MOUNT_PATH = "/data"
STORE_DB_FILENAME = "recheck.db"

_isdir = os.path.isdir
_ismount = os.path.ismount
_writable = os.access


def _nearest_existing_dir(path: str) -> str:
    d = os.path.dirname(os.path.abspath(path))
    while d != "/" and not os.path.exists(d):
        d = os.path.dirname(d)
    return d


def _path_is_persistent(path: str) -> bool:
    """True when the directory that will hold `path` is a mount point
    (a volume). "/" itself is always a mount and proves nothing, so a
    path with no mounted ancestor above the root is ephemeral."""
    d = _nearest_existing_dir(path)
    return d != "/" and _ismount(d)


def resolve_recheck_db() -> tuple[str, bool]:
    """Resolve (db_path, persistent) for the recheck store."""
    explicit = os.environ.get("STALLROW_RECHECK_DB", "").strip()
    if explicit:
        return explicit, _path_is_persistent(explicit)
    if (
        _isdir(VOLUME_MOUNT_PATH)
        and _ismount(VOLUME_MOUNT_PATH)
        and _writable(VOLUME_MOUNT_PATH, os.W_OK)
    ):
        candidate = os.path.join(VOLUME_MOUNT_PATH, STORE_DB_FILENAME)
        log.info("recheck store: volume mount at %s detected", VOLUME_MOUNT_PATH)
        return candidate, True
    return STORE_DB_FILENAME, False


def units_to_price(units: int) -> str:
    """5000 -> '$0.005' (the string format the x402 SDK expects)."""
    dollars = units / 1_000_000
    s = f"{dollars:.6f}".rstrip("0").rstrip(".")
    return f"${s}"


@dataclass(frozen=True)
class Settings:
    pay_to: str
    network: str
    facilitator_url: str
    service_name: str
    port: int
    rpc_url: str
    blockscout_base_url: str
    fetch_timeout_s: float
    github_token: str | None = None
    prices: dict[str, str] = field(default_factory=dict)  # path -> "$x.xx"
    # Coinbase CDP facilitator credentials (optional). Only used when
    # X402_FACILITATOR_URL points at CDP — see use_cdp below.
    cdp_api_key_id: str | None = None
    cdp_api_key_secret: str | None = None
    # Recheck watch state (sqlite): watch baselines AND sold watch-pack
    # balances in one file. Durability depends on where the file lives
    # — see resolve_recheck_db(): a path under a mounted volume (e.g.
    # a Railway Volume at /data) survives redeploys; the container's
    # own disk is wiped by them. `recheck_db_persistent` is the
    # MEASURED durability of the resolved path, reported in /health.
    recheck_db_path: str = "recheck.db"
    recheck_db_persistent: bool = False
    # Solana rail (second x402 payment network for the Fleet Check
    # routes in SOLANA_ACCEPT_PATHS; see app/solana_rail.py). Unlike
    # Token Verdict's fleet-wide rail this one is NOT env-gated off:
    # the Fleet Check dual-accept ships live, with the payTo / network
    # / mint still env-overridable exactly as on Token Verdict.
    solana_pay_to: str = SOLANA_OWNER_WALLET
    solana_network: str = SOLANA_MAINNET
    solana_usdc_mint: str = SOLANA_USDC_MINT
    solana_rpc_url: str | None = None  # optional: adds blockhash hints to 402s

    @property
    def use_cdp(self) -> bool:
        """True when settlements should run through the CDP facilitator
        with JWT auth — the path that feeds the CDP Bazaar catalog."""
        return (
            "api.cdp.coinbase.com" in self.facilitator_url
            and bool(self.cdp_api_key_id)
            and bool(self.cdp_api_key_secret)
        )

    @property
    def use_payai(self) -> bool:
        """True when settlements run through the PayAI facilitator — the
        path that feeds the PayAI index catalog. URL alone selects it."""
        return "facilitator.payai.network" in self.facilitator_url

    def price_for(self, path: str) -> str:
        return self.prices[path]


def load_settings() -> Settings:
    pay_to = os.environ.get("X402_PAY_TO", OWNER_WALLET).strip()
    if pay_to in PLACEHOLDER_WALLETS:
        raise RuntimeError("X402_PAY_TO is a placeholder address — set a real wallet.")
    if not (pay_to.startswith("0x") and len(pay_to) == 42):
        raise RuntimeError(f"X402_PAY_TO does not look like an EVM address: {pay_to!r}")

    prices = {}
    for path, units in PRICE_UNITS.items():
        env_key = "X402_PRICE_" + path.rsplit("/", 1)[-1].replace("-", "_").upper()
        raw = os.environ.get(env_key, "").strip()
        prices[path] = raw if raw else units_to_price(units)

    cdp = {
        k: (os.environ.get(k, "").strip() or None)
        for k in ("CDP_API_KEY_ID", "CDP_API_KEY_SECRET")
    }

    recheck_db = resolve_recheck_db()

    solana_pay_to = os.environ.get("X402_SOLANA_PAY_TO", SOLANA_OWNER_WALLET).strip()
    from x402.mechanisms.svm.utils import validate_svm_address

    if not validate_svm_address(solana_pay_to):
        raise RuntimeError(f"X402_SOLANA_PAY_TO is not a valid Solana address: {solana_pay_to!r}")

    return Settings(
        pay_to=pay_to,
        network=os.environ.get("X402_NETWORK", BASE_MAINNET).strip(),
        facilitator_url=os.environ.get("X402_FACILITATOR_URL", FACILITATOR_URL).strip(),
        service_name=os.environ.get("X402_SERVICE_NAME", "stall-row").strip(),
        port=int(os.environ.get("PORT", "3000")),
        rpc_url=os.environ.get("BASE_RPC_URL", BASE_RPC_URL).strip(),
        blockscout_base_url=os.environ.get(
            "BLOCKSCOUT_BASE_URL", BLOCKSCOUT_BASE_URL
        ).strip(),
        fetch_timeout_s=float(os.environ.get("STALLROW_FETCH_TIMEOUT_S", "15")),
        github_token=(os.environ.get("GITHUB_TOKEN", "").strip() or None),
        recheck_db_path=recheck_db[0],
        recheck_db_persistent=recheck_db[1],
        solana_pay_to=solana_pay_to,
        solana_network=os.environ.get("X402_SOLANA_NETWORK", SOLANA_MAINNET).strip(),
        solana_usdc_mint=os.environ.get("X402_SOLANA_USDC_MINT", SOLANA_USDC_MINT).strip(),
        solana_rpc_url=os.environ.get("SOLANA_RPC_URL", "").strip() or None,
        prices=prices,
        **{k.lower(): v for k, v in cdp.items() if v is not None},
    )
