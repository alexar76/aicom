"""Who is "us": the hub's ecosystem registry, and the SELF / EXT traffic classes it decides.

The rule (the owner's, 2026-10-02): SELF is the hub itself and the components that are bound
to it and part of ITS ecosystem — deployments we run for this hub. EXT is everybody else,
including outside services connected through a billed rail (a game that buys capabilities
for its players, a sibling ecosystem we happen to host) and anybody who deploys this
open-source code for themselves.

Nothing in a request proves membership, so the hub is told, in one file (``ecosystem.json``,
see ``policy_path``). Two kinds of evidence, judged at two different times:

* **Identity — read time.** A credit account listed under ``self.accounts``. Judged when the
  feed is read, so editing the list re-classifies history: taking an account out turns its
  past calls back into EXT.
* **Where the call came from — write time.** The direct caller's network address
  (``self.networks``) or the wallet that paid (``self.wallets``). Neither is stored, so they
  are judged when the row is written and only the verdict is kept (``caller_class``).

The address rule is deliberately narrow, because the hub's own plumbing makes OUR servers
the direct caller of a great deal of other people's traffic:

* a peer hub routing a stranger's purchase arrives from that hub's address;
* a paid Studio step bought on another hub arrives from the buying hub;
* a subcontract child funded by a stranger's allowance arrives from our provider host.

So an address only ever vouches for calls that carry no payer identity (sandbox trials, the
MCP gateway, bare calls). A billed call is judged by WHO paid (the account, or the wallet),
never by where it came from, and a forwarded call is never SELF at all: the routing hub,
which saw the real buyer, is the one that classifies it.

Fail direction: everything that can turn a row SELF is unforgeable from outside (a resolved
client address, an authenticated account, an on-chain payer); everything a caller can send
(routing headers, a federation visitor id) can only push a row towards EXT.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FILE_NAME = "ecosystem.json"

TRAFFIC_SELF = "operator_self"
TRAFFIC_EXTERNAL = "external"

OPERATOR_SELF = "operator_self"

# caller_class values — what was decided when the row was written. '' = nothing; the label
# decides at read time. The SELF verdicts name WHICH entry matched (a short digest of it, not
# the address or wallet), so taking a mistaken entry out of the file turns its rows back into
# EXT: the evidence is gone, but the verdict stays revocable.
CALLER_ADDRESS = "address"      # address:<ref> — an unbilled call straight from a listed server
CALLER_WALLET = "wallet"        # wallet:<ref> — an x402 call paid by a listed wallet
CALLER_FORWARDED = "forwarded"  # a peer hub / seller operation / relay acting for someone else
CALLER_EXTERNAL = "external"    # matched an external.* entry: never SELF
CALLER_CLASSES = ("", CALLER_FORWARDED, CALLER_EXTERNAL)  # plus the address:/wallet: refs
_REF_LEN = 10


def entry_ref(value: Any) -> str:
    """Short, stable digest of one entry (``str(network)`` or a lower-case wallet)."""
    import hashlib
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:_REF_LEN]


def valid_caller_class(value: Any) -> bool:
    text = str(value or "")
    if text in CALLER_CLASSES:
        return True
    kind, _, ref = text.partition(":")
    return kind in (CALLER_ADDRESS, CALLER_WALLET) and len(ref) == _REF_LEN and set(ref) <= _HEX


# traffic_basis published next to traffic_class: why a row is what it is.
BASIS_OPERATOR = "operator"
BASIS_ACCOUNT = "account"
BASIS_OVERRIDE = "override"

# The only labels an address may vouch for: no payer, and not a trial visitor. A sandbox:<id>
# names a visitor; arriving from a server rather than a browser, it is almost always a relay
# (a factory executor, a portal bridge, a game backend) carrying a stranger.
_ADDRESS_LABELS = ("anonymous",)
_ADDRESS_PREFIXES = ("mcp:",)

_SAFE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.@")
_HEX = set("0123456789abcdef")
_MAX_ENTRIES = 10_000

# Addresses that can never be "a server of ours" from the hub's point of view. Every one of
# them is an address the hub's own plumbing presents for OTHER people's calls: loopback is
# where the MCP gateway and the in-process bridges re-enter, a docker gateway or a container
# address is how a host process or a neighbour container arrives, and a hub with no proxy
# trust sees its proxy for every caller. Named ranges, deliberately not is_private /
# is_global: is_private also covers the documentation ranges, which examples and tests use.
_REFUSED_NETS = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4",
    "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
))
_MAPPED_V4 = ipaddress.ip_network("::ffff:0:0/96")
# IPv6 prefixes that stand for IPv4 hosts behind a translator: an entry inside one of them
# would vouch for whole swathes of the IPv4 internet on a NAT64-fronted hub.
_TRANSLATION_NETS = tuple(ipaddress.ip_network(n) for n in (
    "64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "::/96",
))
# Broader than this is a typo or a hosting provider's block, not a few servers: a lazily
# widened entry would make every other customer of that provider SELF.
_MIN_PREFIX = {4: 24, 6: 56}


@dataclass(frozen=True)
class EcosystemPolicy:
    """One loaded ``ecosystem.json`` (plus AIMARKET_OPERATOR_ACCOUNTS). Immutable."""

    self_accounts: frozenset[str] = frozenset()
    external_accounts: frozenset[str] = frozenset()
    self_networks: tuple[Any, ...] = ()
    external_networks: tuple[Any, ...] = ()
    self_wallets: frozenset[str] = frozenset()
    external_wallets: frozenset[str] = frozenset()
    # default | env | file | file+env
    source: str = "default"
    # absent (no file) | ok | partial (some entries refused) | invalid (file rejected)
    status: str = "absent"
    # For the operator's log and `python -m aimarket_hub.ecosystem check`; never published.
    problems: tuple[str, ...] = ()
    loaded_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_net_refs", tuple((n, entry_ref(n)) for n in self.self_networks))
        object.__setattr__(self, "_self_refs", frozenset(
            [f"{CALLER_ADDRESS}:{entry_ref(n)}" for n in self.self_networks]
            + [f"{CALLER_WALLET}:{entry_ref(w)}" for w in self.self_wallets]))

    # ── write time ────────────────────────────────────────────────────────────
    def caller_class(self, *, label: str, client_ip: str = "", payer_wallet: str = "",
                     forwarded: bool = False) -> str:
        """What the write site can decide that the stored row cannot show later.

        ``payer_wallet`` must be a payer verified on chain (x402); ``forwarded`` is true for a
        peer hub's forward, a seller operation, or a relay that announced itself.
        """
        ip = parse_ip(client_ip)
        wallet = normalize_wallet(payer_wallet)
        label = str(label or "").strip()
        # A verified payer is evidence even inside a forward: the seller hub verified it.
        if wallet and label == "x402":
            if wallet in self.external_wallets:
                return CALLER_EXTERNAL
            if wallet in self.self_wallets:
                return f"{CALLER_WALLET}:{entry_ref(wallet)}"
        if forwarded:
            return CALLER_FORWARDED
        if ip is not None and _within(ip, self.external_networks):
            return CALLER_EXTERNAL
        if ip is None or not (label in _ADDRESS_LABELS or label.startswith(_ADDRESS_PREFIXES)):
            # Billed rails are judged by who paid (the registry, at read time); a channel id
            # arrives in a header and vouches for nothing; trials may be relayed visitors.
            return ""
        for net, ref in self._net_refs:  # type: ignore[attr-defined]
            if ip.version == net.version and ip in net:
                return f"{CALLER_ADDRESS}:{ref}"
        return ""

    # ── read time ─────────────────────────────────────────────────────────────
    def classify(self, label: str, caller_class: str = "", hub_url: str = "") -> tuple[str, str | None]:
        """``(traffic_class, traffic_basis)`` for one stored row. Mirrors ``sql_self_condition``
        exactly, including on odd legacy labels (no stripping here that SQL would not do)."""
        lab = str(label or "")
        if lab in _operator_variants(hub_url):
            return TRAFFIC_SELF, BASIS_OPERATOR
        cc = str(caller_class or "")
        if cc == CALLER_FORWARDED:
            return TRAFFIC_EXTERNAL, CALLER_FORWARDED
        if cc == CALLER_EXTERNAL:
            return TRAFFIC_EXTERNAL, BASIS_OVERRIDE
        if lab.startswith("account:"):
            acct = lab[len("account:"):]
            if acct in self.external_accounts:
                return TRAFFIC_EXTERNAL, BASIS_OVERRIDE
            if acct in self.self_accounts:
                return TRAFFIC_SELF, BASIS_ACCOUNT
        if cc in self._self_refs:  # type: ignore[attr-defined]
            return TRAFFIC_SELF, cc.partition(":")[0]
        return TRAFFIC_EXTERNAL, None

    def sql_self_condition(self, hub_url: str = "") -> tuple[str, list[str]]:
        """A WHERE condition true exactly for the rows ``classify`` calls SELF.

        One condition, so a row that is SELF for two reasons is still counted once. Hub URLs
        are matched with and without the trailing slash, so no dialect-specific RTRIM.
        """
        label = "COALESCE(consumer_hub, '')"
        cc = "COALESCE(caller_class, '')"
        op = sorted(_operator_variants(hub_url))
        ext_acc = sorted(f"account:{a}" for a in self.external_accounts)
        self_acc = sorted(f"account:{a}" for a in self.self_accounts)
        refs = sorted(self._self_refs)  # type: ignore[attr-defined]
        params: list[str] = list(op)
        sql = f"({label} IN ({_marks(op)})) OR ({cc} NOT IN ('{CALLER_FORWARDED}', '{CALLER_EXTERNAL}')"
        if ext_acc:
            sql += f" AND {label} NOT IN ({_marks(ext_acc)})"
            params.extend(ext_acc)
        either: list[str] = []
        if self_acc:
            either.append(f"{label} IN ({_marks(self_acc)})")
            params.extend(self_acc)
        if refs:
            either.append(f"{cc} IN ({_marks(refs)})")
            params.extend(refs)
        if not either:
            either.append("1 = 0")
        sql += " AND (" + " OR ".join(either) + "))"
        return sql, params

    # ── published ─────────────────────────────────────────────────────────────
    def public_summary(self) -> dict[str, Any]:
        """How many entries the rule has — never the entries (our servers, account ids)."""
        return {
            "schema": SCHEMA_VERSION,
            "source": self.source,
            "status": self.status,
            "self": {"accounts": len(self.self_accounts), "networks": len(self.self_networks),
                     "wallets": len(self.self_wallets)},
            "external": {"accounts": len(self.external_accounts),
                         "networks": len(self.external_networks),
                         "wallets": len(self.external_wallets)},
            "problems": len(self.problems),
            "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.loaded_at)),
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def operator_labels(hub_url: str = "") -> tuple[str, ...]:
    """Labels that are the hub itself: the admin sentinel, `local`, the hub's own URL."""
    labels = [OPERATOR_SELF, "local"]
    base = str(hub_url or "").strip().rstrip("/")
    if base:
        labels.append(base)
    return tuple(labels)


def _operator_variants(hub_url: str = "") -> frozenset[str]:
    out = set()
    for base in operator_labels(hub_url):
        out.update((base, base + "/"))
    return frozenset(out)


def parse_ip(value: Any) -> Any:
    """A client address as an ``ip_address`` (IPv4-mapped IPv6 unwrapped), or None."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    text = text.split("%", 1)[0]  # an IPv6 zone id
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    if ip.version == 6 and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def normalize_wallet(value: Any) -> str:
    text = str(value or "").strip().lower()
    if len(text) == 42 and text.startswith("0x") and set(text[2:]) <= _HEX:
        return text
    return ""


def normalize_account(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 64 or not set(text) <= _SAFE_ID_CHARS:
        return ""
    return text


def _within(ip: Any, networks: tuple[Any, ...]) -> bool:
    return any(ip.version == net.version and ip in net for net in networks)


def _marks(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def _trusted_proxy_ips() -> list[Any]:
    out = []
    for part in os.environ.get("AIMARKET_TRUSTED_PROXIES", "").split(","):
        ip = parse_ip(part)
        if ip is not None:
            out.append(ip)
    return out


def _parse_network(value: str, proxies: list[Any]) -> tuple[Any | None, str]:
    text = str(value or "").strip()
    if not text:
        return None, "empty network"
    try:
        net = ipaddress.ip_network(text, strict=False)
    except ValueError:
        return None, f"not an IP address or network: {text!r}"
    if net.version == 6 and net.subnet_of(_MAPPED_V4) and net.prefixlen >= 96:
        mapped = net.network_address.ipv4_mapped
        net = ipaddress.ip_network(f"{mapped}/{net.prefixlen - 96}", strict=False)
    for refused in _TRANSLATION_NETS:
        if net.version == refused.version and net.overlaps(refused):
            return None, f"{text}: an IPv4-translation prefix (NAT64/6to4), not a server of ours"
    if net.prefixlen < _MIN_PREFIX[net.version]:
        return None, (f"{text}: broader than /{_MIN_PREFIX[net.version]} — list your servers, "
                      "not a provider's block (it would make strangers SELF)")
    for refused in _REFUSED_NETS:
        if net.version == refused.version and net.overlaps(refused):
            return None, (f"{text}: loopback/private/link-local/container ranges are where the "
                          "hub's own plumbing and proxies arrive from, never a server of ours")
    for proxy in proxies:
        if proxy.version == net.version and proxy in net:
            return None, f"{text}: contains a trusted proxy ({proxy}); every unforwarded call would be SELF"
    return net, ""


# ── loading ───────────────────────────────────────────────────────────────────

_TOP_KEYS = {"version", "self", "external", "comment"}
_KINDS = ("accounts", "networks", "wallets")


def policy_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    """AIMARKET_ECOSYSTEM_FILE, else ``ecosystem.json`` next to the hub database, else ./data."""
    explicit = os.environ.get("AIMARKET_ECOSYSTEM_FILE", "").strip()
    if explicit:
        return Path(explicit)
    db = str(db_path or "").strip() or os.environ.get("AIMARKET_DB_PATH", "").strip()
    if db:
        return Path(db).expanduser().parent / FILE_NAME
    return Path("data") / FILE_NAME


def env_accounts() -> tuple[str, ...]:
    """AIMARKET_OPERATOR_ACCOUNTS — the older way to list our accounts; merged into self."""
    out = []
    for part in os.environ.get("AIMARKET_OPERATOR_ACCOUNTS", "").replace(",", " ").split():
        acct = "".join(c for c in part if c in _SAFE_ID_CHARS)[:64]
        if acct:
            out.append(acct)
    return tuple(out)


def _entry_values(raw: Any, where: str, problems: list[str]) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{where} must be a list")
    if len(raw) > _MAX_ENTRIES:
        raise ValueError(f"{where} has more than {_MAX_ENTRIES} entries")
    values = []
    for i, item in enumerate(raw):
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict):
            extra = set(item) - {"value", "note"}
            if extra or not isinstance(item.get("value"), str):
                problems.append(f"{where}[{i}]: an entry is a string or {{\"value\": …, \"note\": …}}")
                continue
            values.append(item["value"])
        else:
            problems.append(f"{where}[{i}]: an entry is a string or {{\"value\": …, \"note\": …}}")
    return values


def parse_policy(data: Any, *, extra_accounts: tuple[str, ...] = (),
                 proxies: list[Any] | None = None) -> EcosystemPolicy:
    """Validate a decoded ecosystem.json. Raises ValueError when the file must be rejected.

    Structural mistakes (unknown keys, wrong types, wrong version) reject the whole file —
    a misspelt ``"netwroks"`` would otherwise silently drop a list. A single bad value is
    skipped and reported, and the rest applies.
    """
    if not isinstance(data, dict):
        raise ValueError("the file must hold a JSON object")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise ValueError(f"unknown top-level keys: {sorted(unknown)} (allowed: {sorted(_TOP_KEYS)})")
    if data.get("version") != SCHEMA_VERSION:
        raise ValueError(f"\"version\" must be {SCHEMA_VERSION}")
    if proxies is None:
        proxies = _trusted_proxy_ips()
    problems: list[str] = []
    parsed: dict[str, dict[str, Any]] = {}
    for section in ("self", "external"):
        block = data.get(section) or {}
        if not isinstance(block, dict):
            raise ValueError(f"\"{section}\" must be an object")
        unknown = set(block) - set(_KINDS)
        if unknown:
            raise ValueError(f"unknown keys in \"{section}\": {sorted(unknown)} (allowed: {list(_KINDS)})")
        accounts, networks, wallets = set(), [], set()
        for value in _entry_values(block.get("accounts"), f"{section}.accounts", problems):
            acct = normalize_account(value)
            if acct and len(acct) == 12 and set(acct) <= _HEX:
                problems.append(f"{section}.accounts: {value!r} looks like the 12-hex digest the public "
                                "feed shows, not an account id (acct_…)")
            elif acct:
                accounts.add(acct)
            else:
                problems.append(f"{section}.accounts: not an account id: {value!r}")
        for value in _entry_values(block.get("networks"), f"{section}.networks", problems):
            net, why = _parse_network(value, proxies if section == "self" else [])
            if net is not None:
                if net not in networks:
                    networks.append(net)
            else:
                problems.append(f"{section}.networks: {why}")
        for value in _entry_values(block.get("wallets"), f"{section}.wallets", problems):
            wallet = normalize_wallet(value)
            if wallet:
                wallets.add(wallet)
            else:
                problems.append(f"{section}.wallets: not a 0x wallet address: {value!r}")
        parsed[section] = {"accounts": accounts, "networks": networks, "wallets": wallets}

    self_accounts = parsed["self"]["accounts"] | {a for a in extra_accounts if a}
    ext = parsed["external"]
    both = (self_accounts & ext["accounts"]) | (parsed["self"]["wallets"] & ext["wallets"])
    if both:
        problems.append(f"{len(both)} entr{'y is' if len(both) == 1 else 'ies are'} in both lists; external wins")
    overlap = [n for n in parsed["self"]["networks"]
               if any(n.version == e.version and n.overlaps(e) for e in ext["networks"])]
    if overlap:
        problems.append(f"{len(overlap)} self network(s) overlap an external one; external wins")
    return EcosystemPolicy(
        self_accounts=frozenset(self_accounts - ext["accounts"]),
        external_accounts=frozenset(ext["accounts"]),
        self_networks=tuple(parsed["self"]["networks"]),
        external_networks=tuple(ext["networks"]),
        self_wallets=frozenset(parsed["self"]["wallets"] - ext["wallets"]),
        external_wallets=frozenset(ext["wallets"]),
        source="file+env" if extra_accounts else "file",
        status="partial" if problems else "ok",
        problems=tuple(problems),
    )


def _default(extra_accounts: tuple[str, ...], status: str = "absent",
             problems: tuple[str, ...] = ()) -> EcosystemPolicy:
    return EcosystemPolicy(
        self_accounts=frozenset(extra_accounts),
        source="env" if extra_accounts else "default",
        status=status,
        problems=problems,
    )


def load_policy(path: str | os.PathLike[str]) -> EcosystemPolicy:
    """Read and validate one file, without the cache. A missing file is the default rule."""
    extra = env_accounts()
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _default(extra)
    except OSError as exc:
        return _default(extra, "invalid", (f"cannot read {p.name}: {exc.strerror or exc}",))
    if extra:
        logger.warning("ecosystem: AIMARKET_OPERATOR_ACCOUNTS is set as well as %s; its %d "
                       "account(s) are merged into self.accounts — keep the list in one place",
                       p.name, len(extra))
    try:
        return parse_policy(json.loads(text), extra_accounts=extra)
    except (ValueError, json.JSONDecodeError) as exc:
        return _default(extra, "invalid", (f"{p.name} rejected: {exc}",))


_LOCK = threading.Lock()
# path -> (file/env key, policy in force, last policy that loaded ok/partial)
_CACHE: dict[str, tuple[tuple[Any, ...], EcosystemPolicy, EcosystemPolicy | None]] = {}


def _file_key(p: Path) -> tuple[Any, ...]:
    try:
        st = p.stat()
    except OSError:
        return ("missing",)
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def current(path: str | os.PathLike[str] | None = None) -> EcosystemPolicy:
    """The policy in force for ``path`` (default: ``policy_path()``), re-read when it changes.

    One ``stat`` per call — cheap next to the request it serves — so an edit is in force on
    the next call, with no restart. A file that becomes invalid keeps the LAST GOOD policy in
    force (status ``invalid``): a typo while editing must not flip our own traffic to EXT.
    """
    p = Path(path) if path is not None else policy_path()
    key = (_file_key(p), os.environ.get("AIMARKET_OPERATOR_ACCOUNTS", ""),
           os.environ.get("AIMARKET_TRUSTED_PROXIES", ""))
    cache_key = str(p)
    with _LOCK:
        hit = _CACHE.get(cache_key)
        if hit is not None and hit[0] == key:
            return hit[1]
        last_good = hit[2] if hit is not None else None
        fresh = load_policy(p)
        if fresh.status in ("ok", "partial"):
            last_good = fresh
        if fresh.status == "invalid" and last_good is not None:
            fresh = replace(last_good, status="invalid", problems=fresh.problems,
                            loaded_at=time.time())
            logger.error("ecosystem: %s is invalid — keeping the last good policy: %s",
                         p, "; ".join(fresh.problems[:3]))
        elif fresh.status == "invalid":
            logger.error("ecosystem: %s is invalid and there is no earlier good version — only the "
                         "hub itself is SELF until it is fixed: %s", p, "; ".join(fresh.problems[:3]))
        elif fresh.problems:
            logger.warning("ecosystem: %s loaded with problems (%s): %s",
                           p, fresh.status, "; ".join(fresh.problems[:5]))
        _CACHE[cache_key] = (key, fresh, last_good)
        return fresh


def _clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def _main(argv: list[str]) -> int:
    """``python -m aimarket_hub.ecosystem check [FILE]`` — validate before the hub sees it."""
    if not argv or argv[0] != "check":
        print("usage: python -m aimarket_hub.ecosystem check [FILE]", file=sys.stderr)
        return 64
    path = Path(argv[1]) if len(argv) > 1 else policy_path()
    if len(argv) > 1 and not path.exists():
        print(f"{path}: no such file", file=sys.stderr)
        return 1
    policy = load_policy(path)
    summary = policy.public_summary()
    print(f"{path}: {policy.status} (source: {policy.source})")
    print(f"  self:     {summary['self']['accounts']} accounts, {summary['self']['networks']} networks, "
          f"{summary['self']['wallets']} wallets")
    print(f"  external: {summary['external']['accounts']} accounts, {summary['external']['networks']} "
          f"networks, {summary['external']['wallets']} wallets")
    for problem in policy.problems:
        print(f"  ! {problem}")
    return {"ok": 0, "absent": 0, "partial": 2}.get(policy.status, 1)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))
