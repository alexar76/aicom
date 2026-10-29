"""Offline IP→ASN resolver backed by the free iptoasn.com TSV dump.

No API key required: https://iptoasn.com/data/ip2asn-combined.tsv.gz
(see scripts/install_iptoasn.sh). Row format:
``range_start\trange_end\tAS_number\tcountry\tAS_description`` with AS 0 =
not routed. Lookups are bisect over sorted range starts, separately per IP
version (IPv4 and IPv6 integer spaces overlap).
"""

from __future__ import annotations

import gzip
import logging
import os
import threading
from array import array
from bisect import bisect_right
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TSV_CANDIDATES = (
    "./ip2asn-combined.tsv",
    "./geoip/ip2asn-combined.tsv",
)

_CACHE_MAX = 50000


@dataclass(frozen=True)
class AsnInfo:
    asn: int | None
    org: str | None
    #: Registry-allocated country for the range. Field 4 of the iptoasn dump,
    #: which this parser previously read straight past — while SKOPOS asked
    #: geojs.io for the same answer, one visitor address at a time.
    country: str | None = None


_EMPTY = AsnInfo(asn=None, org=None, country=None)


def resolve_tsv_path(explicit: str | None = None) -> str | None:
    """First existing TSV path: explicit arg → env → default locations (+.gz)."""
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("SKOPOS_ASN_TSV_PATH", "").strip()
    if env:
        candidates.append(env)
    candidates.extend(DEFAULT_TSV_CANDIDATES)
    for cand in candidates:
        p = Path(cand).expanduser()
        if p.is_file():
            return str(p)
        gz = Path(str(p) + ".gz")
        if gz.is_file():
            return str(gz)
    return None


class AsnResolver:
    """Lazy-loading range table; safe no-op when the TSV is absent."""

    def __init__(self, tsv_path: str | None = None):
        self._path = resolve_tsv_path(tsv_path)
        self._loaded = False
        self._lock = threading.Lock()
        # per IP version: (sorted starts, ends, asn array, org-index array).
        # IPv4 fits array('Q'); IPv6 ints exceed 64 bits → plain lists.
        # Orgs are deduplicated into self._orgs (~1.1M rows, ~80k unique orgs)
        # to keep the combined dump at tens of MB instead of hundreds.
        self._tables: dict[int, tuple] = {}
        self._orgs: list[str] = []
        #: ~250 distinct values, so the per-range cost is one index, not a string.
        self._ccs: list[str] = []
        self._cache: dict[str, AsnInfo] = {}

    @property
    def has_data(self) -> bool:
        self._ensure_loaded()
        return bool(self._tables)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_locked()
            self._loaded = True

    def _load_locked(self) -> None:
        if not self._path:
            return
        try:
            opener = gzip.open if self._path.endswith(".gz") else open
            rows: dict[int, list[tuple[int, int, int, int, int]]] = {4: [], 6: []}
            org_index: dict[str, int] = {}
            orgs: list[str] = []
            cc_index: dict[str, int] = {}
            ccs: list[str] = []
            with opener(self._path, "rt", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 5:
                        continue
                    try:
                        start = ip_address(parts[0].strip())
                        end = ip_address(parts[1].strip())
                        asn = int(parts[2])
                    except ValueError:
                        continue
                    # 4294967295 = max 32-bit ASN; larger values are bogus rows.
                    if asn <= 0 or asn > 4294967295 or start.version != end.version:
                        continue
                    cc = parts[3].strip().upper()
                    if len(cc) != 2 or not cc.isalpha():
                        cc = ""
                    ci = cc_index.get(cc)
                    if ci is None:
                        ci = len(ccs)
                        cc_index[cc] = ci
                        ccs.append(cc)
                    org = parts[4].strip()
                    if not org or org in ("-", "Not routed"):
                        org = ""
                    oi = org_index.get(org)
                    if oi is None:
                        oi = len(orgs)
                        org_index[org] = oi
                        orgs.append(org)
                    rows[start.version].append((int(start), int(end), asn, oi, ci))
            self._orgs = orgs
            self._ccs = ccs
            for version, items in rows.items():
                if not items:
                    continue
                items.sort(key=lambda r: r[0])
                if version == 4:
                    self._tables[4] = (
                        array("Q", (r[0] for r in items)),
                        array("Q", (r[1] for r in items)),
                        array("L", (r[2] for r in items)),
                        array("L", (r[3] for r in items)),
                        array("H", (r[4] for r in items)),
                    )
                else:
                    self._tables[6] = (
                        [r[0] for r in items],
                        [r[1] for r in items],
                        array("L", (r[2] for r in items)),
                        array("L", (r[3] for r in items)),
                        array("H", (r[4] for r in items)),
                    )
        except Exception:
            # Cached failure — do not re-parse every 5s poll cycle.
            logger.warning("iptoasn TSV load failed: %s", self._path, exc_info=True)
            self._tables = {}
            self._orgs = []
            self._ccs = []

    def lookup(self, ip: str | None) -> AsnInfo:
        ip = (ip or "").strip()
        if not ip:
            return _EMPTY
        cached = self._cache.get(ip)
        if cached is not None:
            return cached
        info = self._lookup_uncached(ip)
        if len(self._cache) >= _CACHE_MAX:
            self._cache.clear()
        self._cache[ip] = info
        return info

    def _lookup_uncached(self, ip: str) -> AsnInfo:
        try:
            addr = ip_address(ip)
        except ValueError:
            return _EMPTY
        mapped = getattr(addr, "ipv4_mapped", None)
        if mapped is not None:  # ::ffff:1.2.3.4 → look up in the v4 table
            addr = mapped
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return _EMPTY
        self._ensure_loaded()
        table = self._tables.get(addr.version)
        if not table:
            return _EMPTY
        starts, ends, asns, org_ids, cc_ids = table
        value = int(addr)
        idx = bisect_right(starts, value) - 1
        if idx < 0 or value > ends[idx]:
            return _EMPTY
        org = self._orgs[org_ids[idx]]
        cc = self._ccs[cc_ids[idx]] if self._ccs else ""
        return AsnInfo(asn=asns[idx], org=org or None, country=cc or None)


_RESOLVERS: dict[str, AsnResolver] = {}


def get_resolver(tsv_path: str | None = None) -> AsnResolver:
    """Process-wide resolver cache — the TSV parse is expensive (~1.1M rows).

    The empty key (no TSV found) is re-resolved on every call, so installing
    the dump later is picked up without a restart; a parsed table is cached
    for the process lifetime.
    """
    key = resolve_tsv_path(tsv_path) or ""
    resolver = _RESOLVERS.get(key)
    if resolver is None:
        resolver = AsnResolver(tsv_path)
        _RESOLVERS[key] = resolver
    return resolver
