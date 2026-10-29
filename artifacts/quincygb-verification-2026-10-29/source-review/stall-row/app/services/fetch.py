"""The fetch stalls: YouTube search scraping, page→Markdown, GitHub
repo vitals. Honesty rule: an upstream failure raises UpstreamError —
the handler returns 502 and the x402 middleware does not settle, so a
buyer is never charged for undelivered data.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from html import unescape as html_unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from ..rpc import UpstreamError

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


# --- YouTube search -------------------------------------------------------------

def parse_youtube_results(html: str, max_results: int) -> list[dict]:
    """Extract video results from a YouTube search page's ytInitialData."""
    marker = "ytInitialData"
    idx = html.find(marker)
    if idx < 0:
        raise UpstreamError("YouTube search page did not contain ytInitialData")
    start = html.find("{", idx)
    if start < 0:
        raise UpstreamError("YouTube search page: malformed ytInitialData")
    depth = 0
    end = None
    in_str = False
    esc = False
    for i in range(start, len(html)):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise UpstreamError("YouTube search page: unterminated ytInitialData")
    try:
        data = json.loads(html[start:end])
    except ValueError as e:
        raise UpstreamError(f"YouTube search page: ytInitialData not JSON: {e}") from e

    results: list[dict] = []

    def walk(node):
        if len(results) >= max_results:
            return
        if isinstance(node, dict):
            vr = node.get("videoRenderer")
            if isinstance(vr, dict) and vr.get("videoId"):
                title = ""
                try:
                    title = vr["title"]["runs"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    title = (vr.get("title") or {}).get("simpleText", "")
                channel = ""
                try:
                    channel = vr["ownerText"]["runs"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    pass
                results.append(
                    {
                        "title": title,
                        "video_id": vr["videoId"],
                        "url": f"https://www.youtube.com/watch?v={vr['videoId']}",
                        "channel": channel or None,
                        "duration": (vr.get("lengthText") or {}).get("simpleText"),
                        "views": (vr.get("viewCountText") or {}).get("simpleText"),
                    }
                )
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return results


async def tube_search(client: httpx.AsyncClient, query: str, max_results: int) -> dict:
    try:
        resp = await client.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=_UA,
            follow_redirects=True,
        )
    except httpx.HTTPError as e:
        raise UpstreamError(f"YouTube fetch failed: {e}") from e
    if resp.status_code != 200:
        raise UpstreamError(f"YouTube returned HTTP {resp.status_code}")
    results = parse_youtube_results(resp.text, max_results)
    if not results:
        raise UpstreamError("YouTube page parsed but contained no video results")
    return {"query": query, "count": len(results), "results": results}


# --- page → markdown ---------------------------------------------------------------

def ssrf_check(url: str) -> None:
    """Reject non-http(s) URLs and any host resolving to a private,
    loopback, link-local, reserved, or multicast address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"host does not resolve: {host}") from e
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"URL host resolves to a non-public address ({ip})")


# Fetch hardening (2026-10-24): production paid calls failed three ways —
# a transient upstream 503 (example.com), a bot-filter 403 (Wikipedia),
# and a plain-text llms.txt that the HTML extractor scored as "no main
# content". The machinery below retries transient failures with backoff,
# answers a 403 with the descriptive User-Agent robot policies ask for,
# follows redirects manually so every hop is SSRF-checked before it is
# fetched, caps the body size, decodes charsets explicitly, and serves
# text/plain + text/markdown bodies as text instead of failing them.

# A descriptive UA, used after a 403: Wikimedia's robot policy (and many
# others) refuses impersonating browser UAs from datacenter egress but
# accepts an identified bot.
_DESCRIPTIVE_UA = {
    "User-Agent": (
        "StallRow/1.0 (+https://stall-row-production.up.railway.app; "
        "page-to-markdown fetcher)"
    )
}
_PAGE_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "text/plain;q=0.8,text/markdown;q=0.8,*/*;q=0.5"
)
_PAGE_HEADERS_BASE = {"Accept": _PAGE_ACCEPT, "Accept-Language": "en-US,en;q=0.9"}

_MAX_PAGE_BYTES = 5 * 1024 * 1024  # fail cleanly past 5 MiB
_MAX_REDIRECTS = 5
_FETCH_ATTEMPTS = 3
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_BACKOFF_S = (0.5, 1.5)

_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_TEXT_TYPES = frozenset({"text/plain", "text/markdown", "text/x-markdown"})
_MIN_FALLBACK_WORDS = 15


async def _read_capped(resp: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in resp.aiter_bytes():
        total += len(chunk)
        if total > _MAX_PAGE_BYTES:
            raise UpstreamError(
                f"page exceeds the {_MAX_PAGE_BYTES // (1024 * 1024)} MiB size limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _get_following_redirects(
    client: httpx.AsyncClient, url: str, headers: dict
) -> tuple[str, int, httpx.Headers, bytes | None]:
    """One GET with manual redirect following: every redirect target is
    SSRF-checked BEFORE it is fetched (client-level following would only
    let us check the final URL, after the target was already contacted).
    The body is read (size-capped) only on a 200."""
    current = url
    for hop in range(_MAX_REDIRECTS + 1):
        async with client.stream(
            "GET", current, headers=headers, follow_redirects=False
        ) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    raise UpstreamError(
                        f"page returned HTTP {resp.status_code} without a Location header"
                    )
                if hop == _MAX_REDIRECTS:
                    raise UpstreamError("page redirected too many times")
                target = urljoin(current, location)
                # getaddrinfo is blocking DNS — keep it off the event loop.
                await asyncio.to_thread(ssrf_check, target)
                current = target
                continue
            body = await _read_capped(resp) if resp.status_code == 200 else None
            return current, resp.status_code, resp.headers, body
    raise UpstreamError("page redirected too many times")  # pragma: no cover


async def _fetch_page(
    client: httpx.AsyncClient, url: str
) -> tuple[str, httpx.Headers, bytes]:
    """Fetch one page with retries. Transient statuses (429/5xx) and
    transport errors retry with backoff under the browser UA; a 403
    (bot filter) switches the next attempt to the descriptive UA.
    Deterministic failures (hard 404, dead host after retries, …) raise
    UpstreamError, so the handler 502s and no payment settles."""
    use_descriptive = False
    last_error = "page fetch failed"
    for attempt in range(_FETCH_ATTEMPTS):
        if attempt:
            await asyncio.sleep(_BACKOFF_S[attempt - 1])
        headers = {
            **(_DESCRIPTIVE_UA if use_descriptive else _UA),
            **_PAGE_HEADERS_BASE,
        }
        try:
            final_url, status, resp_headers, body = await _get_following_redirects(
                client, url, headers
            )
        except httpx.HTTPError as e:
            last_error = f"page fetch failed: {e}"
            continue
        if status == 200:
            assert body is not None  # read exactly on 200 above
            return final_url, resp_headers, body
        last_error = f"page returned HTTP {status}"
        if status == 403:
            use_descriptive = True
            continue
        if status in _RETRY_STATUSES:
            continue
        raise UpstreamError(last_error)
    raise UpstreamError(last_error)


def _decode_body(body: bytes, headers: httpx.Headers) -> str:
    """Decode with the declared charset, then a <meta charset>, then
    UTF-8; never raise on a bad label or a stray byte."""
    charset = None
    m = re.search(
        r"charset=([\w.:-]+)", headers.get("content-type", ""), re.IGNORECASE
    )
    if m:
        charset = m.group(1)
    if not charset:
        head = body[:4096].decode("ascii", errors="ignore")
        m = re.search(r"<meta[^>]+charset=[\"']?([\w.:-]+)", head, re.IGNORECASE)
        if m:
            charset = m.group(1)
    for enc in (charset, "utf-8"):
        if not enc:
            continue
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:512].lower()
    return head.startswith(("<!doctype html", "<html")) or "<html" in head[:256]


def _normalize_text(text: str) -> str:
    """Light normalization for plain-text deliveries: unify newlines,
    trim trailing spaces, collapse 2+ blank lines to one."""
    lines = [
        ln.rstrip()
        for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    out: list[str] = []
    blanks = 0
    for ln in lines:
        if ln.strip():
            out.append(ln)
            blanks = 0
        else:
            blanks += 1
            if blanks == 1:
                out.append("")
    return "\n".join(out).strip("\n")


def _text_title(normalized: str) -> str | None:
    """A Markdown document's leading '# ' heading is its title."""
    for ln in normalized.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if s.startswith("# "):
            return s[2:].strip() or None
        return None
    return None


class _VisibleText(HTMLParser):
    """Collect visible text with block boundaries as newlines; script,
    style, head and template content is not visible text."""

    _SKIP = frozenset({"script", "style", "head", "template", "svg"})
    _BLOCK = frozenset(
        {
            "address", "article", "aside", "blockquote", "br", "dd", "div",
            "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
            "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
            "main", "nav", "ol", "p", "pre", "section", "table", "tr",
            "ul",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def _visible_text(html_text: str) -> str:
    parser = _VisibleText()
    try:
        parser.feed(html_text)
    except Exception:  # noqa: BLE001 — malformed HTML: keep what parsed
        pass
    raw = "".join(parser.parts)
    squashed = "\n".join(
        re.sub(r"[ \t]+", " ", ln) for ln in raw.split("\n")
    )
    return _normalize_text(squashed)


def _extract_markdown(text: str) -> str | None:
    """Main-content extraction. CPU-bound (trafilatura heuristics, with
    the visible-text fallback), so page_to_markdown runs it via
    asyncio.to_thread: on the event loop it would stall every other
    route sharing this process for the length of the crunch."""
    import trafilatura

    markdown = trafilatura.extract(
        text, output_format="markdown", include_links=True, include_images=False
    )
    if not markdown:
        # Trafilatura's heuristics reject some real pages (odd structure,
        # link-dense indexes). Fall back to the page's visible text —
        # but only when there is enough of it to be a delivery, not
        # boilerplate dressed up as content.
        fallback = _visible_text(text)
        if len(fallback.split()) >= _MIN_FALLBACK_WORDS:
            markdown = fallback
    return markdown


async def page_to_markdown(client: httpx.AsyncClient, url: str) -> dict:
    await asyncio.to_thread(ssrf_check, url)  # blocking DNS — off the loop
    final_url, headers, body = await _fetch_page(client, url)
    text = _decode_body(body, headers)
    ctype = headers.get("content-type", "").split(";")[0].strip().lower()

    if ctype in _TEXT_TYPES and not _looks_like_html(text):
        markdown = _normalize_text(text)
        if not markdown:
            raise UpstreamError("page returned no readable text content")
        return {
            "url": url,
            "final_url": final_url,
            "title": _text_title(markdown),
            "markdown": markdown,
            "word_count": len(markdown.split()),
        }

    if (
        ctype
        and ctype not in _HTML_TYPES
        and ctype not in _TEXT_TYPES
        and not _looks_like_html(text)
    ):
        raise UpstreamError(f"unsupported content type: {ctype}")

    markdown = await asyncio.to_thread(_extract_markdown, text)
    if not markdown:
        raise UpstreamError("no main content could be extracted from the page")
    title = None
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if m:
        cleaned = html_unescape(re.sub(r"<[^>]+>", "", m.group(1)))
        title = re.sub(r"\s+", " ", cleaned).strip() or None
    return {
        "url": url,
        "final_url": final_url,
        "title": title,
        "markdown": markdown,
        "word_count": len(markdown.split()),
    }


# --- GitHub repo vitals -------------------------------------------------------------

def parse_repo_input(repo: str) -> str:
    repo = repo.strip()
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", repo)
    if m:
        return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"
    parts = [p for p in repo.split("/") if p]
    if len(parts) == 2 and all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts):
        return repo
    raise ValueError("repo must be 'owner/name' or a github.com URL")


async def repo_vitals(
    client: httpx.AsyncClient, repo: str, github_token: str | None
) -> dict:
    full = parse_repo_input(repo)
    headers = {"Accept": "application/vnd.github+json", **_UA}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    try:
        resp = await client.get(f"https://api.github.com/repos/{full}", headers=headers)
    except httpx.HTTPError as e:
        raise UpstreamError(f"GitHub fetch failed: {e}") from e
    if resp.status_code == 404:
        raise UpstreamError(f"GitHub repo not found: {full}")
    if resp.status_code != 200:
        raise UpstreamError(f"GitHub returned HTTP {resp.status_code}")
    body = resp.json()

    stars = body.get("stargazers_count") or 0
    forks = body.get("forks_count") or 0
    issues = body.get("open_issues_count") or 0
    archived = bool(body.get("archived"))
    pushed_at = body.get("pushed_at")

    score = 50
    notes = []
    if archived:
        score -= 40
        notes.append("Repository is archived (read-only).")
    if stars >= 1000:
        score += 20
        notes.append("Well-starred (≥1,000).")
    elif stars >= 100:
        score += 10
        notes.append("Moderately starred (≥100).")
    elif stars < 10:
        score -= 5
        notes.append("Very few stars (<10).")
    if forks >= 100:
        score += 5
    score = max(0, min(100, score))
    if archived:
        verdict = "Repository is archived — no ongoing development."
    elif score >= 70:
        verdict = "Healthy, established repository."
    elif score >= 45:
        verdict = "Active-looking repository with a modest footprint."
    else:
        verdict = "Thin footprint — small or quiet repository."
    return {
        "repo": full,
        "url": body.get("html_url"),
        "description": body.get("description"),
        "stars": stars,
        "forks": forks,
        "open_issues": issues,
        "license": (body.get("license") or {}).get("spdx_id"),
        "pushed_at": pushed_at,
        "created_at": body.get("created_at"),
        "archived": archived,
        "health_score": score,
        "health_notes": notes,
        "verdict": verdict,
    }
