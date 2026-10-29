from __future__ import annotations

from urllib.parse import urlparse

# path prefix -> virtual host (when nginx log has no $host)
_PATH_HOSTS: tuple[tuple[str, str], ...] = (
    ("/metis", "metis.modelmarket.dev"),
    ("/lottery", "lottery.modelmarket.dev"),
    ("/platon", "platon.modelmarket.dev"),
    ("/family", "family.modelmarket.dev"),
    ("/chronos", "chronos.modelmarket.dev"),
    ("/fermat", "fermat.modelmarket.dev"),
    ("/landauer", "landauer.modelmarket.dev"),
    ("/percola", "percola.modelmarket.dev"),
    ("/ablation", "ablation.modelmarket.dev"),
    ("/dioscuri", "dioscuri.modelmarket.dev"),
    ("/helios", "helios.modelmarket.dev"),
    ("/oracle", "oracles.modelmarket.dev"),
    ("/monitor", "monitor.modelmarket.dev"),
    ("/pulse", "pulse.modelmarket.dev"),
    ("/arena", "arena.modelmarket.dev"),
    ("/argus", "arena.modelmarket.dev"),
)

_SERVER_DEFAULTS: dict[str, list[str]] = {
    "oracle": [
        "oracles.modelmarket.dev",
        "lottery.modelmarket.dev",
        "basanos.modelmarket.dev",
    ],
    "factory": [
        "modelmarket.dev",
        "magic-ai-factory.com",
        "modeldev.modelmarket.dev",
        "themis.modelmarket.dev",
    ],
    "metis": [
        "metis.modelmarket.dev",
    ],
}


def host_from_referer(referer: str | None) -> str | None:
    if not referer:
        return None
    ref = referer.strip()
    if not ref or ref == "-":
        return None
    try:
        if "://" not in ref:
            ref = "http://" + ref
        hostname = urlparse(ref).hostname
        if not hostname or "." not in hostname:
            return None
        h = hostname.lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return None


def _host_from_path(path: str) -> str | None:
    p = path or ""
    if "/.well-known/ai-market" in p or p.startswith("/ai-market"):
        return "modelmarket.dev"
    if p.startswith("/landing") or "modeldev" in p:
        return "modeldev.modelmarket.dev"
    for prefix, host in _PATH_HOSTS:
        if p.startswith(prefix):
            return host
    if p.startswith("/api/") or p.startswith("/_next/") or p in ("/", "/sw.js", "/robots.txt", "/favicon.ico"):
        return None  # ambiguous — need referer or server context
    return None


def infer_host(
    path: str | None,
    *,
    server_name: str | None = None,
    ecosystem_segment: str | None = None,
    referer: str | None = None,
) -> str | None:
    """Guess domain when nginx log_format omits $host."""
    h = host_from_referer(referer)
    if h:
        return h

    p = path or ""
    h = _host_from_path(p)
    if h:
        return h

    seg = ecosystem_segment or ""
    if seg == "factory":
        return "magic-ai-factory.com"
    if seg == "modeldev-landing":
        return "modeldev.modelmarket.dev"
    if seg == "oracles":
        return "oracles.modelmarket.dev"
    if seg == "lottery":
        return "lottery.modelmarket.dev"
    if seg == "basanos":
        return "basanos.modelmarket.dev"
    if seg == "themis":
        return "themis.modelmarket.dev"

    # Last resort: primary domain for collector server (not the only domain on host).
    defaults = _SERVER_DEFAULTS.get(server_name or "", [])
    return defaults[0] if defaults else None


def known_hosts_for_server(server_name: str) -> list[str]:
    return list(_SERVER_DEFAULTS.get(server_name, []))
