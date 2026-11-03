"""Unified multi-chain network selection + health-checked RPC failover (EVM **and** Solana).

This is the single source of truth for *which chain the ecosystem talks to* and *how it
reaches it reliably*. The AIMarket stack is multi-chain: the same escrow + lottery exist
as EVM contracts (Base/Ethereum/Arbitrum — `contracts/evm`, `lottery/contracts`,
`acex/contracts/evm`) **and** as Solana programs (`contracts/solana`). At runtime exactly
one network is active; our live demo deployment is on **Base**.

Two responsibilities:

1. **Network registry + selection.** A preset per network (EVM or Solana) carrying its
   kind, chain-id / cluster, a *priority-ordered* RPC list, native token, explorer, and our
   deployed contract/program addresses. The active network is chosen by env var, defaulting
   to **Base with our demo contracts**. Any other EVM network can be added purely via env
   (no code change): set ``AIMARKET_CHAIN``, ``AIMARKET_CHAIN_KIND=evm``,
   ``AIMARKET_CHAIN_ID`` and ``AIMARKET_RPC_<ID>``.

2. **Health-checked RPC failover.** Both EVM and Solana speak JSON-RPC 2.0 over HTTP, so a
   single :class:`RpcPool` serves both — only the health probe differs (``eth_chainId`` vs
   ``getHealth``). The pool always prefers the **highest-priority endpoint that is healthy**
   (so a working default wins), fails over to the next on error, and *re-probes* a demoted
   endpoint after a cooldown so it **returns to the preferred default once it recovers**.
   Every call is bounded by a short timeout, so an offline environment fails fast instead
   of hanging.

The module is dependency-free (stdlib ``urllib`` transport, injectable for tests) so it can
be vendored verbatim into standalone services (e.g. alien-monitor) and imported directly by
``aimarket_hub`` consumers (the hub, and web/backend which already imports ``aimarket_hub``).

Environment contract
--------------------
``AIMARKET_CHAIN`` / ``AIMARKET_NETWORK``  active network id (default ``base``).
``AIMARKET_TESTNET`` = 1|true              use the testnet variant of the active network.
``AIMARKET_RPC_<ID>``                       comma-separated RPC URLs, **priority order**, e.g.
                                            ``AIMARKET_RPC_BASE="https://my.node,https://backup"``.
                                            Tried ahead of the built-in public presets (deduped),
                                            so your node becomes the preferred default.
``AIMARKET_CHAIN_KIND`` / ``AIMARKET_CHAIN_ID``  define an ad-hoc EVM network not in the presets.
``AIMARKET_ADDR_<ID>_<NAME>``               override/add a contract address for a network, e.g.
                                            ``AIMARKET_ADDR_BASE_ESCROW=0x...``.
``AIMARKET_RPC_TIMEOUT``                     per-call timeout seconds (default 6).
``AIMARKET_RPC_RETRIES``                     repeat attempts per endpoint after transport failure
                                            (default 1, maximum 3).
``AIMARKET_RPC_COOLDOWN``                    seconds a failed endpoint is skipped before re-probe
                                            (default 30).
``AIMARKET_RPC_MAX_COOLDOWN``                maximum exponential cooldown for repeatedly failing
                                            endpoints (default 300). A node that refuses (HTTP
                                            429/403/5xx, a rate or block-range limit) rests at
                                            least as long as its ``Retry-After`` asks.
``AIMARKET_RPC_USER_AGENT``                  User-Agent sent to RPC providers (default
                                            ``aimarket-chain-net/1.0``). Needed because many public
                                            RPCs (Cloudflare-fronted) 403 the default urllib UA.

Back-compat: the legacy single-URL vars (``BASE_RPC_URL``, ``ETHEREUM_RPC_URL``,
``ARBITRUM_RPC_URL``, ``SOLANA_RPC_URL`` and the web layer's
``AIFACTORY_PAYMENT_RPC_{BASE,ETHEREUM,ARBITRUM,SOLANA}``) are still honoured as a
*lower-priority* source, so existing deployments keep working and simply gain failover.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)

# ── chain kinds ──────────────────────────────────────────────────────────────
EVM = "evm"
SOLANA = "solana"

DEFAULT_NETWORK = "base"

# Transport: (url, json_body, timeout_s) -> decoded JSON dict. Injectable for tests.
Transport = Callable[[str, dict, float], dict]


class ChainNetError(RuntimeError):
    """Base error for the chain-net layer."""


class AllEndpointsDown(ChainNetError):
    """Every RPC endpoint for the network failed health/transport — fail closed, do not hang."""


class RpcError(ChainNetError):
    """The RPC node returned a JSON-RPC ``error`` object (a node-level, non-transport failure)."""


# ═════════════════════════════════════════════════════════════════════════════
# Network registry
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class NetworkSpec:
    id: str
    kind: str                       # EVM | SOLANA
    display_name: str
    chain_id: Optional[int]         # EVM numeric chainId; None for Solana
    cluster: Optional[str]          # Solana cluster ("mainnet-beta"); None for EVM
    rpc_urls: tuple[str, ...]       # priority-ordered; index 0 is the preferred default
    native_symbol: str
    explorer_tx: str                # "{}"-formatted url for a tx, "" if unknown
    addresses: dict[str, str] = field(default_factory=dict)  # NAME -> address/program-id
    testnet: bool = False

    @property
    def is_evm(self) -> bool:
        return self.kind == EVM

    @property
    def is_solana(self) -> bool:
        return self.kind == SOLANA

    def explorer_url(self, tx_hash: str) -> str:
        return self.explorer_tx.format(tx_hash) if self.explorer_tx else ""


# Our live Base deployment. Canonical record: docs/onchain-journal.md.
# These are the "demo contracts" the default network ships with; overridable via
# AIMARKET_ADDR_BASE_<NAME>.
#
# There is NO inline address table here on purpose. The one hand-edited source is
# config/deployments/<network>-mainnet.json; scripts/sync_deployment_addresses.py copies
# it into this package's deployments/ directory as package data, so a standalone install
# resolves it too. A duplicated dict is a redeploy waiting to go half-applied.
# Filename of the committed deployment registry for a given network id.
DEPLOYMENT_REGISTRY = "config/deployments/{network}-mainnet.json"


def _load_deployment_contracts(network: str, fallback: dict[str, str] | None = None) -> dict[str, str]:
    """Load the committed address registry for ``network``.

    Search order: AIFACTORY_DEPLOYMENTS_DIR/<network>-mainnet.json, this package's own
    deployments/ directory (package data, written by the sync script), then walk up to
    find config/deployments/<network>-mainnet.json (monorepo checkout). Returns ``{}``
    when none resolve — an empty address map degrades to "no default contracts", which is
    honest, where a stale hard-coded table silently points at the wrong deployment.
    """
    candidates: list[str] = []
    env_dir = os.environ.get("AIFACTORY_DEPLOYMENTS_DIR", "").strip()
    if env_dir:
        candidates.append(os.path.join(env_dir, f"{network}-mainnet.json"))
    here = os.path.dirname(os.path.abspath(__file__))
    # Package data first among the non-env candidates below it: shipped with the wheel,
    # so an off-repo install still gets real addresses instead of nothing.
    candidates.append(os.path.join(here, "deployments", f"{network}-mainnet.json"))
    for _ in range(6):  # walk up to the repo root
        candidates.append(os.path.join(here, "config", "deployments", f"{network}-mainnet.json"))
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            contracts = data.get("contracts")
            if isinstance(contracts, dict) and contracts:
                return {str(k): str(v) for k, v in contracts.items()}
        except (OSError, ValueError):
            continue
    return dict(fallback or {})


_BASE_ADDRESSES: dict[str, str] = _load_deployment_contracts("base")

# Built-in presets. RPC lists are public endpoints in rough reliability order; index 0 is the
# preferred default (matches what the codebase used historically). Backups exist so a single
# provider outage does not take the ecosystem offline.
_PRESETS: dict[str, NetworkSpec] = {
    "base": NetworkSpec(
        id="base", kind=EVM, display_name="Base", chain_id=8453, cluster=None,
        rpc_urls=(
            "https://mainnet.base.org",
            "https://base-rpc.publicnode.com",
            # 2026-10-21, checked from factory-vps and the Independent node: only publicnode and
            # Tenderly's gateway serve eth_getLogs over the deposit watcher's 500-block window;
            # mainnet.base.org answers 429, drpc 400, 1rpc caps it at 50 blocks.
            "https://base.gateway.tenderly.co",
            "https://base.drpc.org",
            "https://1rpc.io/base",
        ),
        native_symbol="ETH",
        explorer_tx="https://basescan.org/tx/{}",
        addresses=dict(_BASE_ADDRESSES),
    ),
    "ethereum": NetworkSpec(
        id="ethereum", kind=EVM, display_name="Ethereum", chain_id=1, cluster=None,
        rpc_urls=(
            "https://eth.llamarpc.com",
            "https://ethereum-rpc.publicnode.com",
            "https://cloudflare-eth.com",
            "https://eth.drpc.org",
            "https://1rpc.io/eth",
        ),
        native_symbol="ETH",
        explorer_tx="https://etherscan.io/tx/{}",
    ),
    "arbitrum": NetworkSpec(
        id="arbitrum", kind=EVM, display_name="Arbitrum One", chain_id=42161, cluster=None,
        rpc_urls=(
            "https://arb1.arbitrum.io/rpc",
            "https://arbitrum-one-rpc.publicnode.com",
            "https://arbitrum.llamarpc.com",
            "https://1rpc.io/arb",
        ),
        native_symbol="ETH",
        explorer_tx="https://arbiscan.io/tx/{}",
    ),
    "solana": NetworkSpec(
        id="solana", kind=SOLANA, display_name="Solana", chain_id=None, cluster="mainnet-beta",
        rpc_urls=(
            "https://api.mainnet-beta.solana.com",
            "https://solana-rpc.publicnode.com",
            "https://1rpc.io/sol",
        ),
        native_symbol="SOL",
        explorer_tx="https://solscan.io/tx/{}",
        # Solana escrow/lottery programs exist in contracts/solana but are not part of the
        # live Base demo; set AIMARKET_ADDR_SOLANA_<NAME> when deployed.
    ),
}

# Testnet variants (chain-id / cluster + RPC) used when AIMARKET_TESTNET is set. Mirrors the
# web payment layer's existing mainnet→sepolia/devnet switch.
_TESTNET: dict[str, dict[str, Any]] = {
    "base": {"chain_id": 84532, "display_name": "Base Sepolia",
             "rpc_urls": ("https://sepolia.base.org", "https://base-sepolia-rpc.publicnode.com")},
    "ethereum": {"chain_id": 11155111, "display_name": "Sepolia",
                 "rpc_urls": ("https://rpc.sepolia.org", "https://ethereum-sepolia-rpc.publicnode.com")},
    "arbitrum": {"chain_id": 421614, "display_name": "Arbitrum Sepolia",
                 "rpc_urls": ("https://sepolia-rollup.arbitrum.io/rpc",)},
    "solana": {"cluster": "devnet", "display_name": "Solana Devnet",
               "rpc_urls": ("https://api.devnet.solana.com",)},
}

# Legacy single-URL env vars to fold in as lower-priority backups (back-compat).
_LEGACY_RPC_ENV: dict[str, tuple[str, ...]] = {
    "base": ("BASE_RPC_URL", "AIFACTORY_PAYMENT_RPC_BASE"),
    "ethereum": ("ETHEREUM_RPC_URL", "AIFACTORY_PAYMENT_RPC_ETHEREUM"),
    "arbitrum": ("ARBITRUM_RPC_URL", "AIFACTORY_PAYMENT_RPC_ARBITRUM"),
    "solana": ("SOLANA_RPC_URL", "AIFACTORY_PAYMENT_RPC_SOLANA"),
}


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _env_bool(name: str) -> bool:
    return _env(name).lower() in ("1", "true", "yes", "on")


def _float_env(name: str, default: float) -> float:
    """Parse a float env var, falling back (with a warning) on a malformed value rather than
    crashing pool construction."""
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        _log.warning("invalid %s=%r — using default %s", name, raw, default)
        return default


def _int_env(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("invalid %s=%r — using default %s", name, raw, default)
        return default


def redact_url(url: str) -> str:
    """Host-only form of an RPC URL, dropping any embedded API key / userinfo / path / query —
    safe to put in error messages and logs."""
    try:
        p = urllib.parse.urlsplit(url)
        host = p.hostname or "?"
        return f"{p.scheme}://{host}" + (f":{p.port}" if p.port else "")
    except Exception:  # noqa: BLE001
        return "<rpc-endpoint>"


_USERINFO_RE = re.compile(r"(https?://)[^/\s@]*@")
_SECRET_QS_RE = re.compile(r"([?&](?:api[_-]?key|key|token|secret|auth)=)[^&\s]*", re.IGNORECASE)


def scrub_secrets(text: str) -> str:
    """Strip credentials from free-text (e.g. an underlying urllib error that embeds the URL):
    drop `//user:pass@` userinfo and redact common secret query params."""
    s = _USERINFO_RE.sub(r"\1", str(text))
    return _SECRET_QS_RE.sub(r"\1REDACTED", s)


def _split_urls(raw: str) -> list[str]:
    return [u.strip() for u in raw.replace("\n", ",").split(",") if u.strip()]


def _dedupe(urls: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        key = u.rstrip("/")
        if key and key not in seen:
            seen.add(key)
            out.append(u)
    return tuple(out)


def _resolve_rpc_urls(net_id: str, preset_urls: tuple[str, ...]) -> tuple[str, ...]:
    """Priority order (deduped, order-preserving):
    1. AIMARKET_RPC_<ID> — the new explicit list, your preferred default first.
    2. Legacy single-URL vars (BASE_RPC_URL, AIFACTORY_PAYMENT_RPC_BASE, …) — these are also
       explicit operator config, so they outrank the public presets.
    3. Built-in public presets — pure backups, so the ecosystem is never fully offline.
    """
    ordered: list[str] = []
    ordered += _split_urls(_env(f"AIMARKET_RPC_{net_id.upper()}"))
    for legacy in _LEGACY_RPC_ENV.get(net_id, ()):
        v = _env(legacy)
        if v:
            ordered.append(v)
    ordered += list(preset_urls)
    return _dedupe(ordered)


def _resolve_addresses(net_id: str, preset_addrs: dict[str, str]) -> dict[str, str]:
    """Preset demo addresses, overlaid with AIMARKET_ADDR_<ID>_<NAME> env overrides."""
    addrs = dict(preset_addrs)
    prefix = f"AIMARKET_ADDR_{net_id.upper()}_"
    for key, val in os.environ.items():
        if key.startswith(prefix) and (val or "").strip():
            addrs[key[len(prefix):]] = val.strip()
    return addrs


def _realm_module() -> Any:
    """The realm seal, when this module is running inside the hub.

    This file is VENDORED verbatim into alien-monitor/backend (a parity test enforces that
    the two are byte-identical), where `aimarket_hub` does not exist — so an unconditional
    import here breaks the monitor at load time. Absent realm means `live` behaviour, which
    is correct for the monitor specifically: it reads chains to draw them and settles
    nothing, so there is no money path for a seal to protect. Inside the hub the import
    always succeeds and the seal always applies.
    """
    try:
        from aimarket_hub import realm

        return realm
    except Exception:
        return None


def network(net_id: Optional[str] = None, *, testnet: Optional[bool] = None) -> NetworkSpec:
    """Resolve a fully-configured :class:`NetworkSpec` (presets + env overrides).

    ``net_id`` defaults to ``AIMARKET_CHAIN``/``AIMARKET_NETWORK`` then ``base``.
    ``testnet`` defaults to the ``AIMARKET_TESTNET`` env flag.
    Unknown ids are allowed if defined ad-hoc via ``AIMARKET_CHAIN_KIND``/``AIMARKET_CHAIN_ID``.
    """
    if net_id is None:
        net_id = _env("AIMARKET_CHAIN") or _env("AIMARKET_NETWORK") or DEFAULT_NETWORK
    net_id = net_id.strip().lower()
    if testnet is None:
        testnet = _env_bool("AIMARKET_TESTNET")

    base_spec = _PRESETS.get(net_id)
    if base_spec is None:
        # Ad-hoc network defined purely via env (the "extensible without code change" path).
        kind = (_env("AIMARKET_CHAIN_KIND") or EVM).lower()
        chain_id_raw = _env("AIMARKET_CHAIN_ID")
        if kind == EVM and chain_id_raw and not chain_id_raw.isdigit():
            _log.warning("ignoring non-numeric AIMARKET_CHAIN_ID=%r for network %r", chain_id_raw, net_id)
        base_spec = NetworkSpec(
            id=net_id, kind=kind, display_name=net_id.title(),
            chain_id=int(chain_id_raw) if (kind == EVM and chain_id_raw.isdigit()) else None,
            cluster=(_env("AIMARKET_CHAIN_CLUSTER") or "mainnet-beta") if kind == SOLANA else None,
            rpc_urls=(), native_symbol=_env("AIMARKET_CHAIN_SYMBOL") or ("SOL" if kind == SOLANA else "ETH"),
            explorer_tx="",
        )

    spec = base_spec
    if testnet and net_id in _TESTNET:
        t = _TESTNET[net_id]
        spec = replace(
            spec,
            display_name=t.get("display_name", spec.display_name),
            chain_id=t.get("chain_id", spec.chain_id),
            cluster=t.get("cluster", spec.cluster),
            rpc_urls=tuple(t.get("rpc_urls", spec.rpc_urls)),
            testnet=True,
        )

    _realm = _realm_module()

    if _realm is not None and _realm.is_uni():
        # The bubble keeps the network's NAME (nothing inside may notice it is not live) and
        # replaces everything that could reach outside: chain id, endpoints, contracts. The
        # preset's public RPC list and the auto-loaded mainnet address table are dropped
        # rather than filtered — a leak here is real money leaving a simulation.
        spec = replace(
            spec,
            chain_id=_realm.uni_chain_id() if spec.kind == EVM else spec.chain_id,
            rpc_urls=(),
            addresses={},
            testnet=False,
        )

    resolved = replace(
        spec,
        rpc_urls=_resolve_rpc_urls(net_id, spec.rpc_urls),
        addresses=_resolve_addresses(net_id, spec.addresses),
    )
    # Fail closed, on every resolve rather than once at startup: env can change between
    # calls (tests do it, and so does a container restart with a new .env), and a spec that
    # escaped the realm is not something to discover after the first payment offer.
    if _realm is not None:
        _realm.assert_sealed(
            chain_id=resolved.chain_id,
            rpc_urls=resolved.rpc_urls,
            addresses=resolved.addresses,
        )
    return resolved


def active_network(*, testnet: Optional[bool] = None) -> NetworkSpec:
    """The currently-selected network (from env), default Base + demo contracts."""
    return network(None, testnet=testnet)


def supported_networks() -> list[str]:
    return list(_PRESETS.keys())


# ═════════════════════════════════════════════════════════════════════════════
# Transport (stdlib default, injectable)
# ═════════════════════════════════════════════════════════════════════════════

# Many public RPC providers (Cloudflare-fronted: base.org, llamarpc, publicnode, drpc, 1rpc…)
# reject the default ``Python-urllib/x.y`` User-Agent with HTTP 403. Send a real UA so the
# health probes and calls actually reach the node. Overridable via AIMARKET_RPC_USER_AGENT.
_DEFAULT_USER_AGENT = "aimarket-chain-net/1.0"


def user_agent() -> str:
    """The User-Agent to send to RPC providers (consumers using web3/httpx should set this too)."""
    return os.getenv("AIMARKET_RPC_USER_AGENT") or _DEFAULT_USER_AGENT


def _urllib_transport(url: str, body: dict, timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": user_agent(),
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed scheme http(s))
        return json.loads(resp.read().decode("utf-8"))


# ═════════════════════════════════════════════════════════════════════════════
# RPC pool with health-checked failover
# ═════════════════════════════════════════════════════════════════════════════

#: A JSON-RPC error that means "this node will not serve that request" — a rate limit or a cap
#: on the block range — rather than "the request is wrong". Another node may serve it, so the
#: pool moves on instead of handing the caller a refusal one provider chose to make.
_REFUSAL_RE = re.compile(
    r"rate.?limit|too many requests|limited to|block range|range (is )?too (large|wide|big)"
    r"|exceeds? (the )?(max|limit)|-32005\b|capacity",
    re.IGNORECASE,
)


def _status_code(exc: BaseException) -> Optional[int]:
    """The HTTP status behind a transport error: urllib's HTTPError (``code``) or httpx's
    HTTPStatusError (``response.status_code``) — read by shape, so neither is imported."""
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    code = getattr(getattr(exc, "response", None), "status_code", None)
    return code if isinstance(code, int) else None


def is_refusal(exc: BaseException) -> bool:
    """A node that is up but will not answer now: HTTP 429/403/5xx or a limit in its reply.
    Asking it again at once only spends the quota it is protecting, so it is not retried."""
    code = _status_code(exc)
    if code is not None:
        return code in (403, 429) or code >= 500
    return bool(_REFUSAL_RE.search(str(exc)))


def retry_after_s(exc: BaseException) -> float:
    """Seconds a refusing node asked us to wait (``Retry-After``), 0 when it did not say."""
    headers = getattr(exc, "headers", None) or getattr(getattr(exc, "response", None), "headers", None)
    try:
        return max(0.0, float((headers or {}).get("retry-after") or (headers or {}).get("Retry-After") or 0))
    except (TypeError, ValueError, AttributeError):
        return 0.0


class _Endpoint:
    __slots__ = ("url", "healthy", "cooldown_until", "fails", "last_error")

    def __init__(self, url: str) -> None:
        self.url = url
        self.healthy = True            # optimistic; first failure demotes it
        self.cooldown_until = 0.0      # monotonic time before which we skip it
        self.fails = 0
        self.last_error = ""

    def mark_ok(self) -> None:
        self.healthy = True
        self.cooldown_until = 0.0
        self.fails = 0
        self.last_error = ""

    def mark_fail(self, cooldown: float, max_cooldown: float, now: float, *,
                  at_least: float = 0.0, error: str = "") -> None:
        self.healthy = False
        self.fails += 1
        delay = min(max_cooldown, cooldown * (2 ** min(self.fails - 1, 10)))
        self.cooldown_until = now + max(delay, min(max_cooldown, at_least))
        self.last_error = error


class RpcPool:
    """Priority-ordered JSON-RPC pool with health-aware failover for EVM **and** Solana.

    ``call``/``run`` always try the highest-priority *eligible* endpoint first (eligible =
    healthy, or cooled-down and due for a re-probe), so a working preferred default is always
    chosen and a recovered default is reclaimed after its cooldown. Transport/RPC failures
    demote an endpoint and fail over to the next; if all are down, raises
    :class:`AllEndpointsDown` (fast — bounded by ``timeout`` per endpoint, no hanging).

    ``rotate=True`` spreads calls instead: each call starts at the next eligible endpoint in
    turn. That is what a caller with many calls against free public nodes wants (the deposit
    watcher reads hundreds of log windows to catch up), since per-IP quotas are what such
    nodes enforce and one preferred node takes every call otherwise.
    """

    def __init__(
        self,
        spec: NetworkSpec,
        *,
        transport: Optional[Transport] = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        cooldown: Optional[float] = None,
        max_cooldown: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        rotate: bool = False,
    ) -> None:
        # Only http(s) endpoints reach the transport — a hard guard against an env-supplied
        # file:// / gopher:// URL turning a health probe into a local-file/SSRF read.
        usable = [u for u in spec.rpc_urls if u.lower().startswith(("http://", "https://"))]
        dropped = [u for u in spec.rpc_urls if u not in usable]
        if dropped:
            _log.warning("ignoring non-http(s) RPC URL(s) for %r: %s",
                         spec.id, [redact_url(u) for u in dropped])
        if not usable:
            raise ChainNetError(
                f"network {spec.id!r} has no usable http(s) RPC URLs configured "
                f"(set AIMARKET_RPC_{spec.id.upper()})"
            )
        self.spec = spec
        self._transport = transport or _urllib_transport
        self._timeout = timeout if timeout is not None else _float_env("AIMARKET_RPC_TIMEOUT", 6.0)
        configured_retries = retries if retries is not None else _int_env("AIMARKET_RPC_RETRIES", 1)
        self._retries = max(0, min(3, configured_retries))
        self._cooldown = cooldown if cooldown is not None else _float_env("AIMARKET_RPC_COOLDOWN", 30.0)
        self._max_cooldown = (
            max_cooldown
            if max_cooldown is not None
            else _float_env("AIMARKET_RPC_MAX_COOLDOWN", 300.0)
        )
        self._clock = clock
        self._endpoints = [_Endpoint(u) for u in usable]
        self._rotate = rotate
        self._turn = 0
        self._turn_lock = threading.Lock()

    # ── endpoint selection ────────────────────────────────────────────────
    def _candidates(self) -> list[_Endpoint]:
        """Priority order, dropping endpoints still inside their cooldown. If every endpoint
        is cooling down, return them all, soonest-rested first (a forced retry beats giving
        up). A rotating pool starts each call one eligible endpoint further on."""
        now = self._clock()
        live = [e for e in self._endpoints if e.healthy or now >= e.cooldown_until]
        if not live:
            return sorted(self._endpoints, key=lambda e: e.cooldown_until)
        if self._rotate and len(live) > 1:
            with self._turn_lock:
                start = self._turn % len(live)
                self._turn += 1
            live = live[start:] + live[:start]
        return live

    def _demote(self, ep: _Endpoint, exc: BaseException) -> None:
        ep.mark_fail(self._cooldown, self._max_cooldown, self._clock(),
                     at_least=retry_after_s(exc), error=" ".join(scrub_secrets(f"{type(exc).__name__}: {exc}").split())[:200])

    def _all_down(self) -> AllEndpointsDown:
        why = "; ".join(f"{redact_url(e.url)}: {e.last_error or 'resting'}" for e in self._endpoints)
        return AllEndpointsDown(f"all {len(self._endpoints)} RPC endpoint(s) for {self.spec.id!r} failed — {why}")

    # ── core call paths ───────────────────────────────────────────────────
    def run(self, fn: Callable[[str], Any]) -> Any:
        """Run ``fn(url)`` against endpoints in priority order, failing over on exception.

        ``fn`` MUST raise only on transport/connection failure (to trigger failover) and
        return normally for a valid answer — including legitimate "not found" results, which
        must be modelled as return values, not exceptions, or they would be retried needlessly.
        """
        for ep in self._candidates():
            for attempt in range(self._retries + 1):
                try:
                    result = fn(ep.url)
                except Exception as exc:  # noqa: BLE001 — any transport error fails over
                    if attempt < self._retries and not is_refusal(exc):
                        continue
                    self._demote(ep, exc)
                    break
                ep.mark_ok()
                return result
        raise self._all_down()

    def call(self, method: str, params: Optional[list] = None) -> Any:
        """Make a JSON-RPC 2.0 call with failover; returns the ``result`` field.

        Raises :class:`RpcError` if a node returns a JSON-RPC ``error`` (this does NOT fail
        over — the request reached a node and was rejected on its merits)."""
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}

        def _do(url: str) -> Any:
            resp = self._transport(url, body, self._timeout)
            if not isinstance(resp, dict):
                # Not a JSON-RPC object → a broken/wrong endpoint. Treat as a transport
                # failure so the pool fails over instead of returning garbage to the caller.
                raise ChainNetError(f"malformed RPC reply (expected object, got {type(resp).__name__})")
            if resp.get("error"):
                # A node-level rejection — surface it without burning the whole pool.
                raise RpcError(f"{method}: {resp['error']}")
            return resp.get("result")

        # RpcError must propagate (not be treated as transport failure), so run a thin loop
        # that fails over on transport errors only — and on a node's refusal (a rate or range
        # limit), which says nothing about the request and is not repeated to the same node.
        for ep in self._candidates():
            for attempt in range(self._retries + 1):
                try:
                    result = _do(ep.url)
                except RpcError as exc:
                    if is_refusal(exc):
                        self._demote(ep, exc)
                        break
                    ep.mark_ok()  # the node answered; it's healthy, the *request* was bad
                    raise
                except Exception as exc:  # noqa: BLE001
                    if attempt < self._retries and not is_refusal(exc):
                        continue
                    self._demote(ep, exc)
                    break
                ep.mark_ok()
                return result
        raise self._all_down()

    # ── health ─────────────────────────────────────────────────────────────
    def _probe_method(self) -> tuple[str, list]:
        return ("getHealth", []) if self.spec.is_solana else ("eth_chainId", [])

    def healthy_url(self) -> Optional[str]:
        """Return the highest-priority endpoint that responds to a health probe, marking
        states along the way; ``None`` if every endpoint is down. Use to gate work (e.g. a
        live feed) so it degrades to "offline" instead of hanging when no node is reachable."""
        method, params = self._probe_method()
        for ep in self._candidates():
            for attempt in range(self._retries + 1):
                try:
                    self._transport(ep.url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, self._timeout)
                except Exception:  # noqa: BLE001
                    if attempt < self._retries:
                        continue
                    ep.mark_fail(self._cooldown, self._max_cooldown, self._clock())
                    break
                ep.mark_ok()
                return ep.url
        return None

    def health(self) -> dict:
        """Full health report across all endpoints (for diagnostics / monitor surfacing)."""
        method, params = self._probe_method()
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        endpoints = []
        any_ok = False
        for ep in self._endpoints:
            ok = False
            detail = ""
            try:
                resp = self._transport(ep.url, body, self._timeout)
                if not isinstance(resp, dict):
                    detail = f"malformed reply ({type(resp).__name__})"  # non-object → unhealthy
                elif resp.get("error"):
                    detail = str(resp.get("error"))
                else:
                    ok = True
                    detail = "ok"
            except Exception as exc:  # noqa: BLE001
                detail = scrub_secrets(f"{type(exc).__name__}: {exc}")
            if ok:
                any_ok = True
                ep.mark_ok()
            else:
                ep.mark_fail(self._cooldown, self._max_cooldown, self._clock())
            endpoints.append({"url": redact_url(ep.url), "healthy": ok, "detail": detail})
        return {
            "network": self.spec.id,
            "kind": self.spec.kind,
            "chain_id": self.spec.chain_id,
            "cluster": self.spec.cluster,
            "healthy": any_ok,
            "endpoints": endpoints,
        }

    def check(self, *, logs_filter: Optional[dict] = None, max_lag: int = 30) -> list[dict]:
        """Ask every EVM endpoint, in list order, what its callers will: the chain id, the head
        and — given ``logs_filter`` (an eth_getLogs filter plus ``window``, its block count) —
        eth_getLogs over that window ending 20 blocks below the node's head. A node can be up
        and still refuse that: public Base nodes answered 429, 400 or "limited to 50 blocks".

        One row per endpoint, URL host-only. ``usable``: the right chain, a head within
        ``max_lag`` blocks of the best one, and the logs answered. Endpoint state is updated
        as a call would update it, so a check also rests the nodes that refused.
        """
        def ask(url: str, method: str, params: list) -> Any:
            resp = self._transport(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, self._timeout)
            if not isinstance(resp, dict):
                raise ChainNetError(f"malformed RPC reply (expected object, got {type(resp).__name__})")
            if resp.get("error"):
                raise RpcError(f"{method}: {resp['error']}")
            return resp.get("result")

        rows: list[dict] = []
        for ep in self._endpoints:
            row: dict[str, Any] = {"url": redact_url(ep.url), "chain_id": None, "head": None, "lag": None,
                                   "logs": "", "ms": None, "usable": False, "detail": ""}
            started = time.monotonic()
            try:
                row["chain_id"] = int(str(ask(ep.url, "eth_chainId", [])), 16)
                row["head"] = int(str(ask(ep.url, "eth_blockNumber", [])), 16)
                if logs_filter is not None:
                    window = max(1, int(logs_filter.get("window", 500)))
                    end = max(0, row["head"] - 20)
                    flt = {k: v for k, v in logs_filter.items() if k != "window"}
                    flt.update(fromBlock=hex(max(0, end - window + 1)), toBlock=hex(end))
                    ask(ep.url, "eth_getLogs", [flt])
                    row["logs"] = "ok"
            except Exception as exc:  # noqa: BLE001 — every failure is a row, not an abort
                # One line: httpx appends "For more information check: …" on a line of its own.
                row["detail"] = " ".join(scrub_secrets(f"{type(exc).__name__}: {exc}").split())[:160]
                if logs_filter is not None and row["head"] is not None:
                    row["logs"] = "refused"
                self._demote(ep, exc)
            else:
                ep.mark_ok()
            row["ms"] = int((time.monotonic() - started) * 1000)
            rows.append(row)
        best = max((r["head"] for r in rows if r["head"] is not None), default=None)
        for r in rows:
            if r["head"] is not None and best is not None:
                r["lag"] = best - r["head"]
            right_chain = r["chain_id"] is not None and (self.spec.chain_id is None or r["chain_id"] == self.spec.chain_id)
            if r["chain_id"] is not None and not right_chain and not r["detail"]:
                r["detail"] = f"answers for chain {r['chain_id']}, not {self.spec.chain_id}"
            r["usable"] = (right_chain and not r["detail"] and r["lag"] is not None and r["lag"] <= max_lag
                           and (logs_filter is None or r["logs"] == "ok"))
        return rows


_POOL_CACHE: dict[tuple[Any, ...], RpcPool] = {}
_POOL_CACHE_LOCK = threading.Lock()


def pool_for(net_id: Optional[str] = None, *, testnet: Optional[bool] = None, **kw: Any) -> RpcPool:
    """Return a process-persistent pool for a network.

    Escrow reads are separate calls. Reusing the pool preserves endpoint health and cooldown
    between them, instead of retrying a known-dead primary on every operation. Callers that
    inject a transport or clock receive an isolated pool, which also keeps tests hermetic.
    """
    spec = network(net_id, testnet=testnet)
    if "transport" in kw or "clock" in kw:
        return RpcPool(spec, **kw)

    timeout = kw.get("timeout")
    retries = kw.get("retries")
    cooldown = kw.get("cooldown")
    max_cooldown = kw.get("max_cooldown")
    resolved_timeout = timeout if timeout is not None else _float_env("AIMARKET_RPC_TIMEOUT", 6.0)
    resolved_retries = retries if retries is not None else _int_env("AIMARKET_RPC_RETRIES", 1)
    resolved_retries = max(0, min(3, resolved_retries))
    resolved_cooldown = cooldown if cooldown is not None else _float_env("AIMARKET_RPC_COOLDOWN", 30.0)
    resolved_max = (
        max_cooldown
        if max_cooldown is not None
        else _float_env("AIMARKET_RPC_MAX_COOLDOWN", 300.0)
    )
    key = (
        spec.id,
        spec.testnet,
        spec.kind,
        spec.chain_id,
        spec.rpc_urls,
        float(resolved_timeout),
        resolved_retries,
        float(resolved_cooldown),
        float(resolved_max),
    )
    with _POOL_CACHE_LOCK:
        pool = _POOL_CACHE.get(key)
        if pool is None:
            pool = RpcPool(
                spec,
                timeout=resolved_timeout,
                retries=resolved_retries,
                cooldown=resolved_cooldown,
                max_cooldown=resolved_max,
            )
            _POOL_CACHE[key] = pool
        return pool


def pool_for_urls(urls: list[str] | tuple[str, ...], *, chain_id: Optional[int] = None, rotate: bool = True,
                  timeout: Optional[float] = None, transport: Optional[Transport] = None) -> RpcPool:
    """A process-persistent rotating pool over an explicit URL list.

    The payment paths build their own lists (``settle.rpc_urls``, ``deposit_verify.rpc_urls_for``)
    because their overrides are EXCLUSIVE — a bubble's node must never fall through to mainnet —
    which a network preset with its public backups would not honour. Keyed by the list, chain,
    rotation, timeout and transport, so the rest a refusing node earned carries over to the
    next call instead of the next call asking it first again.
    """
    clean = tuple(u.strip() for u in urls if u and u.strip())
    key = ("urls", clean, chain_id, rotate, None if timeout is None else float(timeout), transport)
    with _POOL_CACHE_LOCK:
        pool = _POOL_CACHE.get(key)
        if pool is None:
            spec = NetworkSpec(id=f"chain-{chain_id}" if chain_id else "rpc-list", kind=EVM,
                               display_name=f"chain {chain_id}" if chain_id else "RPC list",
                               chain_id=chain_id, cluster=None, rpc_urls=clean, native_symbol="", explorer_tx="")
            pool = RpcPool(spec, transport=transport, timeout=timeout, rotate=rotate)
            _POOL_CACHE[key] = pool
        return pool


def reset_pools() -> None:
    """Forget every cached pool and the rest its endpoints earned (tests, an operator reload)."""
    with _POOL_CACHE_LOCK:
        _POOL_CACHE.clear()
