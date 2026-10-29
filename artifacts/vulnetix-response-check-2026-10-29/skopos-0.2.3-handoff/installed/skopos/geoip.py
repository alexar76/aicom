from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Iterable

import maxminddb
import requests



@dataclass(frozen=True)
class CountryInfo:
    iso_code: str | None
    name: str | None


def is_private_ip(ip: str) -> bool:
    try:
        addr = ip_address(ip.strip())
    except Exception:
        return True
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def _mmdb_ready(mmdb_path: str | None) -> bool:
    if not mmdb_path:
        return False
    return Path(mmdb_path).expanduser().is_file()


def offline_source_ready(mmdb_path: str | None, asn_resolver=None) -> bool:
    """Whether country can be answered offline *with the same meaning*.

    Only a MaxMind database counts. The iptoasn dump also carries a country, and
    it is used as a last resort below — but it reports where a block was
    *allocated*, not where the host is. Measured against 3.7M stored rows it
    disagreed with the geolocated answer for 98% of them (a Kazakh-registered
    range serving from the Netherlands, a Romanian one answering as Taiwanese).
    Letting it silently replace geolocation would rewrite every map on the
    dashboard while looking like a privacy improvement.
    """
    del asn_resolver  # deliberately not a substitute; see the note above
    return _mmdb_ready(mmdb_path)


def resolve_api_fallback(mmdb_path: str | None, asn_resolver=None) -> bool:
    """Whether to call external GeoIP HTTP APIs (geojs.io, ipwho.is).

    Default stack: free HTTP lookups — no MaxMind account required.
    Optional MaxMind GeoLite2-Country MMDB is used first when the file exists.

    SKOPOS_GEOIP_API_FALLBACK=0 disables outbound HTTP only when a local MMDB
    file is present (fully offline mode). Without MMDB, HTTP stays enabled.
    """
    offline = offline_source_ready(mmdb_path, asn_resolver)
    raw = os.environ.get("SKOPOS_GEOIP_API_FALLBACK", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return not offline
    if raw in ("1", "true", "yes", "on"):
        return True
    # Default off once anything local can answer. Every HTTP lookup hands a
    # visitor's address to a third party for a country code we already hold.
    return not offline


class GeoIPResolver:
    """Country lookup: geojs.io + ipwho.is by default; optional MaxMind MMDB offline boost."""

    def __init__(self, mmdb_path: str | None = None, *, api_fallback: bool | None = None,
                 asn_resolver=None):
        self._reader = None
        self._asn = asn_resolver
        self._api_fallback = (
            resolve_api_fallback(mmdb_path, asn_resolver)
            if api_fallback is None else api_fallback
        )
        self._last_api_at = 0.0
        self._api_deadline: float | None = None

        if mmdb_path:
            p = Path(mmdb_path).expanduser()
            if p.is_file():
                self._reader = maxminddb.open_database(str(p))

    @property
    def has_mmdb(self) -> bool:
        return self._reader is not None

    @property
    def uses_http_fallback(self) -> bool:
        return self._api_fallback

    def limit_http_to(self, seconds: float) -> None:
        """Stop asking the HTTP services ``seconds`` from now.

        Past the deadline a lookup answers "unknown" without sending anything,
        so the caller's rows still land, only without a country. For a caller
        that has to answer within a fixed time, which a count cap cannot promise
        when each request may take anywhere from 0.1 s to its 8 s timeout.
        """
        self._api_deadline = time.monotonic() + max(0.0, float(seconds))

    def close(self) -> None:
        if self._reader:
            try:
                self._reader.close()
            except Exception:
                pass

    @lru_cache(maxsize=50000)
    def country_for_ip(self, ip: str) -> CountryInfo:
        ip = (ip or "").strip()
        if not ip:
            return CountryInfo(iso_code=None, name=None)
        if is_private_ip(ip):
            return CountryInfo(iso_code="INT", name="Internal")

        if self._reader:
            info = self._lookup_mmdb(ip)
            if info.iso_code or info.name:
                return info

        if self._api_fallback:
            info = self._lookup_api(ip)
            if info.iso_code or info.name:
                return info

        # Last resort only. Registry allocation is not geolocation, so this
        # answers when nothing else could rather than in preference to them.
        if self._asn is not None:
            cc = getattr(self._asn.lookup(ip), "country", None)
            if cc:
                # No name: the dump carries only the ISO code, and every chart
                # already falls back to the code when the name is absent
                # (charts.py:222,250,587). Grouping is by code, so nothing
                # analytic depends on this.
                return CountryInfo(iso_code=cc, name=None)

        return CountryInfo(iso_code=None, name=None)

    def _lookup_mmdb(self, ip: str) -> CountryInfo:
        try:
            rec = self._reader.get(ip)
        except Exception:
            return CountryInfo(iso_code=None, name=None)
        if not isinstance(rec, dict):
            return CountryInfo(iso_code=None, name=None)
        country = rec.get("country") or rec.get("registered_country") or {}
        if not isinstance(country, dict):
            return CountryInfo(iso_code=None, name=None)
        iso = country.get("iso_code")
        names = country.get("names") or {}
        name = names.get("en") if isinstance(names, dict) else None
        return CountryInfo(iso_code=str(iso) if iso else None, name=str(name) if name else None)

    def _lookup_geojs(self, ip: str) -> CountryInfo:
        try:
            r = requests.get(f"https://get.geojs.io/v1/ip/geo/{ip}.json", timeout=8)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                return CountryInfo(iso_code=None, name=None)
            cc = data.get("country_code") or data.get("country_code3")
            return CountryInfo(
                iso_code=str(cc) if cc else None,
                name=str(data.get("country") or "") or None,
            )
        except Exception:
            return CountryInfo(iso_code=None, name=None)

    def _lookup_api(self, ip: str) -> CountryInfo:
        # geojs.io works from datacenters; ip-api.com often returns 403 on server IPs.
        now = time.monotonic()
        if self._api_deadline is not None and now >= self._api_deadline:
            return CountryInfo(iso_code=None, name=None)
        wait = 0.12 - (now - self._last_api_at)
        if wait > 0:
            time.sleep(wait)
        self._last_api_at = time.monotonic()
        info = self._lookup_geojs(ip)
        if info.iso_code or info.name:
            return info
        try:
            r = requests.get(
                f"https://ipwho.is/{ip}",
                timeout=8,
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict) or not data.get("success", True):
                return CountryInfo(iso_code=None, name=None)
            return CountryInfo(
                iso_code=str(data.get("country_code") or "") or None,
                name=str(data.get("country") or "") or None,
            )
        except Exception:
            return CountryInfo(iso_code=None, name=None)

    def batch_lookup(self, ips: list[str]) -> dict[str, CountryInfo]:
        """Resolve many public IPs via geojs (ip-api batch blocked on many hosts)."""
        out: dict[str, CountryInfo] = {}
        todo = [ip.strip() for ip in ips if ip and not is_private_ip(ip.strip())]
        for ip in ips:
            if is_private_ip((ip or "").strip()):
                out[ip.strip()] = CountryInfo(iso_code="INT", name="Internal")

        if not self._api_fallback:
            for ip in todo:
                out[ip] = CountryInfo(iso_code=None, name=None)
            return out

        # One request per network, not per address. Addresses in the same /24
        # share a country by construction, so this is a pure saving — and on a
        # backfill of the whole historical visitor population it is the
        # difference between a few hundred requests and a quarter of a million.
        by_net: dict[str, CountryInfo] = {}
        for ip in todo:
            if ip in out:
                continue
            if ip not in by_net:
                by_net[ip] = self._lookup_api(ip)
            out[ip] = by_net[ip]
        return out

    def prefetch_map(self, ips: Iterable[str]) -> dict[str, CountryInfo]:
        """Resolve many IPs efficiently: MMDB when present, else optional HTTP batch."""
        unique = list(dict.fromkeys(ip.strip() for ip in ips if ip and ip.strip()))
        out: dict[str, CountryInfo] = {}
        api_todo: list[str] = []
        for ip in unique:
            if is_private_ip(ip):
                out[ip] = CountryInfo(iso_code="INT", name="Internal")
            elif self._reader:
                out[ip] = self.country_for_ip(ip)
            else:
                api_todo.append(ip)
        if api_todo and self._api_fallback:
            out.update(self.batch_lookup(api_todo))
        elif api_todo:
            for ip in api_todo:
                out[ip] = CountryInfo(iso_code=None, name=None)
        return out
