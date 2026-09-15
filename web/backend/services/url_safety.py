"""Validate outbound URLs (git remotes, webhooks) against SSRF and unsafe hosts."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

_ALLOWED_GIT_HOST_SUFFIXES = (
    "github.com",
    "gitlab.com",
    "bitbucket.org",
)

_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal"})


def validate_git_remote_url(url: str) -> str:
    """
    Allow only HTTPS remotes on public git hosts (GitHub / GitLab / Bitbucket).
    Blocks private IPs, loopback, and metadata endpoints.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    if len(raw) > 2048:
        raise ValueError("remote_url too long")
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise ValueError("Git remote must use https://")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Git remote URL missing host")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".local"):
        raise ValueError("Git remote host not allowed")
    if "%" in host:
        raise ValueError("Invalid git remote host")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("Git remote must not target a private or reserved IP")
    else:
        if not any(host == suffix or host.endswith(f".{suffix}") for suffix in _ALLOWED_GIT_HOST_SUFFIXES):
            raise ValueError(
                "Git remote host must be github.com, gitlab.com, or bitbucket.org "
                "(optionally a subdomain)"
            )
    if parsed.username or parsed.password:
        raise ValueError("Credentials in git remote URL are not allowed")
    if re.search(r"[\x00-\x1f]", raw):
        raise ValueError("Invalid characters in remote_url")
    return raw
