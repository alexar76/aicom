from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Healthchecks / internal polling — hide by default in visitor views.
# Anchored prefix match on raw UA (case-insensitive).
SERVICE_UA_PATTERN = re.compile(
    r"(?i)^(?:"
    r"alien-monitor|alienmonitor|node|dioscuri|python-httpx|python-requests|python-urllib|"
    r"TLM-Audit|Go-http-client|curl|wget|okhttp|AIMarketHub|aimarket-hub|"
    r"helios|metis|gaia|platon|theoros|argus|skopos|basanos|themis|git/|pip "
    r")",
)
SERVICE_PATH_PATTERN = re.compile(
    r"(?i)(?:/api/health(?:z|/|$)|/monitor/api/(?:state|argus/run|chain/status|health)|"
    r"/healthz(?:/|$)|/\.well-known/ai-market)",
)

# Prefix LIKE patterns for SQL hide_service (applied to LOWER(user_agent)).
SERVICE_UA_SQL_PREFIXES = (
    "alien-monitor%",
    "alienmonitor%",
    "node%",
    "dioscuri%",
    "python-httpx%",
    "python-requests%",
    "python-urllib%",
    "tlm-audit%",
    "go-http-client%",
    "curl%",
    "wget%",
    "okhttp%",
    "aimarkethub%",
    "aimarket-hub%",
    "helios%",
    "metis%",
    "gaia%",
    "platon%",
    "theoros%",
    "argus%",
    "skopos%",
    "basanos%",
    "themis%",
    "git/%",
    "git %",
    "pip/%",
    "pip %",
)

SERVICE_PATH_SQL_LIKES = (
    "%/api/health",
    "%/api/healthz%",
    "%/healthz",
    "%/monitor/api/state%",
    "%/monitor/api/argus/run%",
    "%/monitor/api/chain/status%",
    "%/monitor/api/health%",
    "%/.well-known/ai-market%",
)

# user_agents.is_bot misses many crawlers/scanners. Used at ingest + SQL Hide bots.
BOT_UA_HINT = re.compile(
    r"(?i)(?:"
    r"\bbot\b|crawl|spider|slurp|scrapy|headless|"
    r"facebookexternalhit|bytespider|semrush|ahrefs|petal|yandex|"
    r"duckduck|baidu|sogou|seznam|applebot|bingpreview|gptbot|"
    r"claudebot|oai-search|360spider|trendiction|dotbot|mj12bot|"
    r"rogerbot|linkedinbot|twitterbot|slackbot|discordbot|telegrambot|"
    r"websiphon|libredtail|l9explore|l9tcpid|zgrab|masscan|nuclei|nikto|"
    r"sqlmap|nmap|nessus|openvas|whatweb|ferox|gobuster|dirbuster|wfuzz|"
    r"localix|palo alto|hello from|hello world|scan(ner)?|probe|audit|^http:"
    r")"
)

# LIKE fragments for SQL hide_bots (lowercase; match LOWER(user_agent/ua_browser)).
BOT_UA_SQL_LIKES = (
    "%bot%",
    "%crawl%",
    "%spider%",
    "%slurp%",
    "%headless%",
    "%facebookexternalhit%",
    "%bytespider%",
    "%semrush%",
    "%ahrefs%",
    "%petalbot%",
    "%yandex%",
    "%duckduck%",
    "%baidu%",
    "%sogou%",
    "%applebot%",
    "%bingpreview%",
    "%gptbot%",
    "%claudebot%",
    "%oai-search%",
    "%360spider%",
    "%trendiction%",
    "%mj12bot%",
    "%dotbot%",
    "%websiphon%",
    "%libredtail%",
    "%l9explore%",
    "%l9tcpid%",
    "%zgrab%",
    "%masscan%",
    "%nuclei%",
    "%nikto%",
    "%sqlmap%",
    "%nmap%",
    "%nessus%",
    "%whatweb%",
    "%ferox%",
    "%gobuster%",
    "%dirbuster%",
    "%wfuzz%",
    "%localix%",
    "%palo alto%",
    "%hello from%",
    "%hello world%",
    "%scanner%",
    "%-scan%",
    "%probe%",
    "%audit%",
    "http:%",
)


# Hosting / cloud / scanner ASN organizations (matched on LOWER(asn_org)).
# Residential eyeball ISPs (Comcast, Cox, AT&T, …) must NOT match — residential
# proxies stay for the page+asset behavioral check in verified visitors.
DATACENTER_ORG_SQL_LIKES = (
    "%hosting%",
    "%hostinger%",
    "%hostwinds%",
    "%hostkey%",
    "%hostroyale%",
    "%dmzhost%",
    "%byteplus%",
    "%bytedance%",
    "%datacenter%",
    "%data center%",
    "%datacamp%",
    "%colocation%",
    "%colocross%",
    "%cloud%",
    "%server%",
    "%vps%",
    "%dedicated%",
    "%digitalocean%",
    "%amazon%",
    "%google cloud%",
    "%google-cloud%",
    "%googlebot%",
    "%microsoft%",
    "%azure%",
    "%oracle-bmc%",
    "%alibaba%",
    "%tencent%",
    "%huawei%",
    "%linode%",
    "%akamai%",
    "%vultr%",
    "%choopa%",
    "%contabo%",
    "%leaseweb%",
    "%hetzner%",
    "%ovh%",
    "%m247%",
    "%gcore%",
    "%g-core%",
    "%selectel%",
    "%timeweb%",
    "%aeza%",
    "%stark industries%",
    "%stark-industries%",
    "%latitude-sh%",
    "%latitude.sh%",
    "%web2objects%",
    "%logicweb%",
    "%oculus networks%",
    "%techoff%",
    "%packethub%",
    "%ipxo%",
    "%namecheap%",
    "%godaddy%",
    "%unifiedlayer%",
    "%censys%",
    "%shodan%",
    "%onyphe%",
    "%binaryedge%",
    "%internet-measurement%",
    "%tenable%",
    "%rapid7%",
    "%netcraft%",
    "%internet vikings%",
    "%agotoz%",
)


def is_datacenter_org(org: str | None) -> bool:
    """True when an iptoasn org string looks like hosting/cloud/scanner space."""
    low = (org or "").strip().lower()
    if not low:
        return False
    return any(frag.strip("%") in low for frag in DATACENTER_ORG_SQL_LIKES)


# ── Verified visitors (GA-comparable "people") ──────────────────────────────
# A "person" is an IP that fetched a page document AND its subresources from a
# non-datacenter network. Replay fleets hit APIs/RSC payloads without ever
# requesting a document; probe bots request documents without assets.
# LIKE fragments applied to LOWER(path).

ASSET_PATH_SQL_LIKES = (
    "%.css%",
    "%.js%",
    "%.mjs%",
    "%.map%",
    "%.png%",
    "%.jpg%",
    "%.jpeg%",
    "%.webp%",
    "%.gif%",
    "%.svg%",
    "%.ico%",
    "%.woff%",
    "%.ttf%",
    "%.otf%",
    "%.webmanifest%",
    "%/assets/%",
    "%/static/%",
    "%/_next/image%",
    "%favicon%",
    "%/fonts/%",
    "%/images/%",
)

# Non-document paths: API calls, data payloads, feeds. Anchored where a bare
# substring would swallow real documents ("/docs/api/overview", "/feedback").
# `%.js%` above already covers `.json`, kept explicit for readability.
NON_PAGE_PATH_SQL_LIKES = (
    "/api/%",
    "%/api/v%",
    "%_rsc=%",
    "%.json%",
    "%.xml%",
    "%.txt%",
    "%.rss%",
    "%/feed",
    "%/feed/%",
    "%/feed.xml%",
    "%/graphql%",
    "%/wp-json%",
)

PAGEVIEW_EXCLUDE_SQL_LIKES = ASSET_PATH_SQL_LIKES + NON_PAGE_PATH_SQL_LIKES

# iCloud Private Relay / consumer VPN egress: real people surf from these
# ASNs (Cloudflare, Akamai, Fastly). The behavioral page+asset gates already
# separate their humans from same-ASN bots, so the verified-visitors
# datacenter gate exempts them (the org strings match %cloud%/%akamai%).
RELAY_EGRESS_ASNS = (13335, 20940, 36183, 54113)


def _like_any(value: str | None, patterns) -> bool:
    """Python mirror of the SQL LIKE lists ('%' wildcard, '_' literal)."""
    import fnmatch

    low = (value or "").lower()
    return any(fnmatch.fnmatchcase(low, p.replace("%", "*")) for p in patterns)


def looks_like_asset_path(path: str | None) -> bool:
    return _like_any(path, ASSET_PATH_SQL_LIKES)


def looks_like_page_path(path: str | None) -> bool:
    """Document-ish path: what a human navigation (GA pageview) fetches."""
    p = (path or "").strip()
    if not p:
        return False
    return not _like_any(p, PAGEVIEW_EXCLUDE_SQL_LIKES)


def looks_like_bot(*, user_agent: str | None = None, ua_browser: str | None = None) -> bool:
    """Heuristic bot/scanner flag beyond user_agents.parse().is_bot."""
    if user_agent is not None:
        ua = user_agent.strip()
        if not ua or ua == "-":
            return True
        if BOT_UA_HINT.search(ua):
            return True
    if ua_browser is not None:
        raw = ua_browser.strip()
        if raw and raw != "-" and BOT_UA_HINT.search(raw):
            return True
    return False


def is_service_traffic(*, user_agent: str | None, path: str | None) -> bool:
    ua = (user_agent or "").strip()
    p = path or ""
    if ua and SERVICE_UA_PATTERN.search(ua):
        return True
    if p and SERVICE_PATH_PATTERN.search(p):
        return True
    return False


def service_traffic_mask(user_agents, paths) -> "pd.Series":
    """Vectorized hide-service mask (True = service traffic)."""
    import pandas as pd

    ua = pd.Series(user_agents, dtype="object").fillna("").astype(str).str.strip()
    path = pd.Series(paths, dtype="object").fillna("").astype(str)
    return ua.str.contains(SERVICE_UA_PATTERN) | path.str.contains(SERVICE_PATH_PATTERN)


def client_label(user_agent: str | None, ua_browser: str | None) -> str:
    ua = (user_agent or "").strip()
    if ua_browser and ua_browser not in ("Other", "None"):
        return ua_browser
    if not ua or ua == "-":
        return "—"
    if ua.startswith("Mozilla/"):
        return ua_browser or "Browser"
    # Service / bot client id: "TLM-Audit-Scanner/1.0" -> TLM-Audit-Scanner
    return ua.split("/")[0][:48] or ua[:48]
