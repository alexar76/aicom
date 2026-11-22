"""site.agent_policy@v1: what does this site's robots.txt let each AI agent do, and what does it
signal?

Give `url`: a domain or an https URL (its path is the one judged; default "/"). Optionally `agents`,
the product tokens to judge (default: a list of AI crawlers and agents, plus "*"), and `path`.

The agent reads https://<host>/robots.txt and applies RFC 9309, as HISTOR's own crawler does:
  - groups (2.1, 2.2.1): one or more user-agent lines then rules; the group naming the product token
    (case-insensitive; "GPTBot/1.1" names GPTBot) is used, several such groups combined; else the
    "*" groups; else everything is allowed;
  - matching (2.2.2, 2.2.3): the path with its query, percent-encoding normalised on both sides, "*"
    any sequence and a final "$" the end; the longest match decides and Allow wins a tie;
    /robots.txt itself is always allowed;
  - access (2.3.1): 2xx is the file; a redirect to the same host is followed (up to five), one to
    another host is reported and not followed; 4xx means "unavailable": everything allowed; 5xx or
    no answer means "unreachable": everything disallowed. Only the first 256 KiB are read (the RFC
    asks for at least 500 KiB; a longer file is reported).
It also reads Content-Signal lines (Cloudflare's Content Signals Policy, draft-romm-aipref-
contentsignals: search, ai-input, ai-train, yes or no). Neither the draft nor the policy says which
agents a line covers; robots.txt grammar puts it in the group it sits in, so each agent gets its
group's signal, and `signal_lines` lists every Content-Signal and Content-Usage (AIPREF) line with
the user-agents of its group, so a line placed under one bot's group is visible as such. Also the
Sitemap lines, and whether /llms.txt exists.

A robots.txt is a request by the site, not an access control; this says what the site asked, as
read at the moment of the call.
"""

import re
from urllib.parse import quote, urlsplit

DEFAULT_AGENTS = (
    "*",
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "Claude-User",
    "Claude-SearchBot",
    "anthropic-ai",
    "Google-Extended",
    "PerplexityBot",
    "Perplexity-User",
    "CCBot",
    "Bytespider",
    "Applebot-Extended",
    "meta-externalagent",
    "Amazonbot",
    "histor",
)
MAX_BYTES = 256 * 1024
MAX_FETCHES = 6
_KEEP = "/?=&;:@!$'()*+,~-._%#[]"
SIGNALS = ("search", "ai-input", "ai-train")


def normalise(value):
    """RFC 9309 2.2.2: compare percent-encoded forms; non-ASCII as UTF-8 escapes, upper-case."""
    return re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group(0).upper(), quote(value, safe=_KEEP))


def _matches(pattern, path):
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*")) + ("$" if anchored else "")
    return re.match(regex, path) is not None


def _names(value, agent):
    token = value.strip().split("/", 1)[0].strip().lower()
    return token == agent.lower()


def parse(text):
    """[(user-agents, rules, content signals)] in file order, sitemaps, stray rules, and every
    Content-Signal and Content-Usage line with the user-agents of the group it sits in."""
    groups, agents, rules, signals = [], [], [], {}
    in_rules, sitemaps, stray, lines = False, [], 0, []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if in_rules:
                groups.append((agents, rules, signals))
                agents, rules, signals, in_rules = [], [], {}, False
            agents.append(value)
        elif key in ("allow", "disallow"):
            if not agents:
                stray += 1
                continue
            in_rules = True
            if value:
                rules.append((key == "allow", normalise(value)))
        elif key in ("content-signal", "content-usage"):
            lines.append(
                {"line": key.title() + ": " + value[:200], "group": list(agents[:10]) or None}
            )
            if key == "content-usage":
                continue
            in_rules = in_rules or bool(agents)
            for item in value.split(","):
                name, eq, setting = item.strip().partition("=")
                name, setting = name.strip().lower(), setting.strip().lower()
                if eq and name in SIGNALS and setting in ("yes", "no"):
                    signals[name] = setting == "yes"
        elif key == "sitemap" and value:
            sitemaps.append(value)
    if agents:
        groups.append((agents, rules, signals))
    return groups, sitemaps, stray, lines


def decide(groups, agent, path):
    named = [g for g in groups if any(_names(n, agent) for n in g[0])]
    group = (
        agent
        if named
        else ("*" if any(any(n.strip() == "*" for n in g[0]) for g in groups) else "")
    )
    chosen = named or [g for g in groups if any(n.strip() == "*" for n in g[0])]
    rules = [r for g in chosen for r in g[1]]
    signals = {}
    for g in chosen:
        signals.update(g[2])
    if path == "/robots.txt":
        return True, None, group, signals
    best = None
    for allow, pattern in rules:
        if not _matches(pattern, path):
            continue
        size = len(pattern.encode())
        if (
            best is None
            or size > len(best[1].encode())
            or (size == len(best[1].encode()) and allow)
        ):
            best = (allow, pattern)
    return best is None or best[0], best, group, signals


def _host(value):
    text = str(value or "").strip()
    if "://" in text:
        parts = urlsplit(text)
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
        ):
            raise ValueError("url must be https on port 443, with no credentials")
        return (parts.hostname or "").lower(), (parts.path or "/") + (
            "?" + parts.query if parts.query else ""
        )
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", text.lower()):
        raise ValueError("url must be a domain such as example.com or an https URL")
    return text.lower(), "/"


def handle(payload):
    if not isinstance(payload, dict):
        raise ValueError("send an object: url, optionally agents and path")
    host, path = _host(payload.get("url"))
    if not host:
        raise ValueError("url names no host")
    if payload.get("path") is not None:
        path = str(payload["path"])
        if not path.startswith("/"):
            raise ValueError("path must start with /")
    agents = payload.get("agents") or list(DEFAULT_AGENTS)
    if (
        not isinstance(agents, list)
        or not 1 <= len(agents) <= 40
        or not all(isinstance(a, str) and re.match(r"^[A-Za-z0-9_*-]{1,64}$", a) for a in agents)
    ):
        raise ValueError("agents must be 1 to 40 product tokens such as GPTBot or *")
    target = normalise(path)
    fetches = 0
    url = "https://" + host + "/robots.txt"
    out = {"host": host, "path": path, "robots_url": url}
    redirects = []
    state, text = None, ""
    for _ in range(MAX_FETCHES - 1):
        fetches += 1
        try:
            reply = fetch(url, headers={"accept": "text/plain"})  # noqa: F821 — the sandbox provides fetch()
        except Exception as exc:  # the hearth refused or could not connect; never the fetch signal
            state, out["robots_error"] = "unreachable", str(exc)[:160]
            break
        out["robots_status"] = reply.status
        if 300 <= reply.status < 400 and reply.headers.get("location"):
            location = reply.headers["location"]
            nxt = (
                location
                if "://" in location
                else "https://" + host + ("" if location.startswith("/") else "/") + location
            )
            parts = urlsplit(nxt)
            redirects.append(nxt)
            if (
                parts.scheme != "https"
                or (parts.hostname or "").lower() != host
                or len(redirects) > 5
            ):
                state = "redirected_elsewhere"
                if parts.scheme == "https" and parts.hostname and parts.hostname.lower() != host:
                    out["next"] = {"url": parts.hostname.lower()}
                break
            url = nxt
            continue
        if 200 <= reply.status < 300:
            state, text = "ok", reply.text
        elif 400 <= reply.status < 500:
            state = "unavailable"
        else:
            state = "unreachable"
        break
    if redirects:
        out["redirects"] = redirects
    out["robots"] = state
    out["verdict"] = state
    if state == "ok" and len(text.encode("utf-8")) >= MAX_BYTES:
        out["warning"] = (
            "the file is 256 KiB or longer; only that much was read here "
            "(RFC 9309 asks for 500 KiB)"
        )
    groups, sitemaps, stray, signal_lines = parse(text) if state == "ok" else ([], [], 0, [])
    if state == "ok":
        out["groups"] = [
            {
                "user_agents": g[0][:20],
                "rules": len(g[1]),
                **({"content_signal": g[2]} if g[2] else {}),
            }
            for g in groups[:60]
        ]
        out["sitemaps"] = sitemaps[:20]
        if stray:
            out["rules_outside_groups"] = stray
        if signal_lines:
            out["signal_lines"] = signal_lines[:20]
    verdicts = []
    for agent in agents:
        row = {"agent": agent}
        if state == "ok":
            allowed, rule, group, signals = decide(groups, agent, target)
            row.update(allowed=allowed, group=group or "none")
            if rule:
                row["rule"] = ("Allow: " if rule[0] else "Disallow: ") + rule[1]
            if signals:
                row["content_signal"] = signals
        elif state == "unavailable":
            row.update(
                allowed=True,
                group="none",
                reason="robots.txt answered "
                + str(out.get("robots_status"))
                + ": RFC 9309 2.3.1.3, everything allowed",
            )
        elif state == "redirected_elsewhere":
            row.update(
                allowed=None,
                reason="robots.txt redirects to another host; call again with url "
                + str(out.get("next", {}).get("url", "that host")),
            )
        else:
            row.update(
                allowed=False,
                group="none",
                reason="robots.txt is unreachable: RFC 9309 2.3.1.4, everything disallowed",
            )
        verdicts.append(row)
    out["agents"] = verdicts
    blocked = [r["agent"] for r in verdicts if r.get("allowed") is False]
    out["disallowed"] = blocked
    if fetches < MAX_FETCHES:
        try:
            llms = fetch("https://" + host + "/llms.txt", headers={"accept": "text/plain"})  # noqa: F821
            body = llms.text if 200 <= llms.status < 300 else ""
            looks = body.lstrip().startswith("#") and "<html" not in body[:500].lower()
            out["llms_txt"] = {"status": llms.status, "present": bool(looks)}
            if looks:
                out["llms_txt"]["title"] = body.lstrip().splitlines()[0].lstrip("# ").strip()[:120]
        except Exception as exc:
            out["llms_txt"] = {"error": str(exc)[:160]}
    return out
