"""
Static HTML/CSS/JS rewrites for sandbox file preview (no FastAPI dependency).

Keeps iframe previews on ``/api/sandbox/file/{id}/…`` — see ``web/backend/api/sandbox.py``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from starlette.requests import Request

# Demo generators often embed http://localhost:PORT/... — inside our iframe that resolves to the
# viewer's machine (connection refused). Rewrite to same-origin-relative paths resolved via <base>.
#
# Apply _LOCALHOST_URL_RE *before* protocol-relative rewrite: ``http://localhost`` contains the
# substring ``//localhost``; rewriting protocol-relative first would corrupt full URLs.
_LOOPBACK_HOST = r"(?:127\.0\.0\.1|localhost|\[::1\])"

_LOCALHOST_URL_RE = re.compile(
    rf"https?://{_LOOPBACK_HOST}(?::\d+)?"
    r"(/[^\"'\s<>]*)?"  # path
    r"(\?[^\"'\s<>]*)?"  # query
    r"(#[^\"'\s<>]*)?",  # fragment
    re.IGNORECASE,
)

# ``href="//localhost/..."`` resolves to http(s)://localhost/... in the browser — escapes the sandbox.
_PROTO_REL_LOCALHOST_RE = re.compile(
    rf"//{_LOOPBACK_HOST}(?::\d+)?"
    r"(/[^\"'\s<>]*)?"
    r"(\?[^\"'\s<>]*)?"
    r"(#[^\"'\s<>]*)?",
    re.IGNORECASE,
)

# Root-absolute URLs (/foo) resolve against the **browser origin**, not <base href>.
_ROOT_ABS_ATTR_RE = re.compile(
    r"(src|href|xlink:href|action|data-src|poster)\s*=\s*"
    r"(['\"])(/[^'\"]*)\2",
    re.IGNORECASE,
)
_CSS_URL_ROOT_ABS_RE = re.compile(
    r"\burl\s*\(\s*(['\"]?)(/[^)'\"\s]+)\1\s*\)",
    re.IGNORECASE,
)
_TARGET_BREAKOUT_RE = re.compile(
    r"\s+target\s*=\s*([\"'])(?:_top|_parent)\1",
    re.IGNORECASE,
)
_JS_LOCATION_ROOT_RE = re.compile(
    r"\b(?:window\.)?location(?:\.href)?\s*=\s*(['\"])(/[^'\"]+)\1",
    re.IGNORECASE,
)
_JS_OPEN_ROOT_RE = re.compile(
    r"\b(?:window\.)?open\s*\(\s*(['\"])(/[^'\"]+)\1",
    re.IGNORECASE,
)


def _rewrite_localhost_urls(text: str) -> str:
    """Turn absolute localhost URLs into ./path?s#frag so <base href=/api/sandbox/file/.../> applies."""

    def _repl(m: re.Match[str]) -> str:
        path, query, frag = m.group(1), m.group(2) or "", m.group(3) or ""
        if not path or path == "/":
            base = "./"
        else:
            base = "." + path
        return base + query + frag

    text = _LOCALHOST_URL_RE.sub(_repl, text)
    text = _PROTO_REL_LOCALHOST_RE.sub(_repl, text)
    return text


def _rewrite_root_absolute_paths(text: str) -> str:
    """Rewrite root-absolute paths to ./… so they honor sandbox <base href>."""

    def _attr_repl(m: re.Match[str]) -> str:
        attr, quote, path = m.group(1), m.group(2), m.group(3)
        if path.startswith("//"):
            return m.group(0)
        if path == "/":
            new_path = "./"
        else:
            new_path = "." + path
        return f"{attr}={quote}{new_path}{quote}"

    out = _ROOT_ABS_ATTR_RE.sub(_attr_repl, text)

    def _css_url_repl(m: re.Match[str]) -> str:
        quote, path = m.group(1), m.group(2)
        if path.startswith("//"):
            return m.group(0)
        new_path = "./" if path == "/" else "." + path
        inner = f"{quote}{new_path}{quote}" if quote else new_path
        return f"url({inner})"

    out = _CSS_URL_ROOT_ABS_RE.sub(_css_url_repl, out)

    def _quoted_root_swap(m: re.Match[str]) -> str:
        quote, path = m.group(1), m.group(2)
        if path.startswith("//"):
            return m.group(0)
        new_path = "./" if path == "/" else "." + path
        return m.group(0).replace(f"{quote}{path}{quote}", f"{quote}{new_path}{quote}", 1)

    out = _JS_LOCATION_ROOT_RE.sub(_quoted_root_swap, out)
    out = _JS_OPEN_ROOT_RE.sub(_quoted_root_swap, out)
    return out


def _neutralize_iframe_breakouts(html: str) -> str:
    """Remove target=_top/_parent so navigation stays inside the demo iframe."""
    return _TARGET_BREAKOUT_RE.sub("", html)


def inject_preview_api_fetch_shim(html: str, sandbox_id: str) -> str:
    """Rewrite browser fetch('/api/…') to the sandbox reverse-proxy prefix (live FastAPI preview)."""
    sid = re.sub(r"[^\w\-]", "", sandbox_id)
    if not sid:
        return html
    shim = (
        '<script id="aicom-sandbox-api-proxy">'
        "(function(){var BASE='/api/sandbox/backend/" + sid + "';"
        "function rewrite(u){if(typeof u!=='string')return u;if(u.indexOf(BASE)===0)return u;"
        "if(u.startsWith('/api/'))return BASE+u;return u;}"
        "var of=window.fetch;window.fetch=function(input,init){"
        "try{if(typeof input==='string')return of(rewrite(input),init);"
        "if(typeof Request!=='undefined'&&input instanceof Request){var nu=rewrite(input.url);"
        "if(nu!==input.url)input=new Request(nu,input);}}"
        "catch(e){}"
        "return of.call(window,input,init);};})();</script>"
    )
    m = re.search(r"<base\s[^>]*>", html, re.I)
    if m:
        return html[: m.end()] + shim + html[m.end() :]
    m2 = re.search(r"<head[^>]*>", html, re.I)
    if m2:
        return html[: m2.end()] + shim + html[m2.end() :]
    return shim + html


def inject_html_base_href(html: str, base_href: str) -> str:
    """Inject ``<base href>``; strip conflicting ``<base>`` (e.g. generator localhost bases)."""
    html = re.sub(r"<base\s[^>]*>", "", html, flags=re.I)
    tag = f'<base href="{base_href}">'
    m = re.search(r"<head[^>]*>", html, re.I)
    if m:
        return html[: m.end()] + tag + html[m.end() :]
    return tag + html


def public_origin_from_request(request: Request | None) -> str:
    """
    Browser-facing origin (scheme + host[:port]), honoring reverse-proxy headers.
    Empty string means caller should use root-relative URLs only.
    """
    if request is None:
        return ""
    try:
        xf_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
        host = xf_host or (request.headers.get("host") or "").strip()
        if not host:
            return ""
        xf_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        scheme = xf_proto or getattr(request.url, "scheme", None) or "http"
        return f"{scheme}://{host}".rstrip("/")
    except Exception:
        return ""


def sandbox_static_base_href(sandbox_id: str, request: Request | None = None) -> str:
    """``<base href>`` for static files under ``/api/sandbox/file/{id}/`` (absolute when possible)."""
    path = f"/api/sandbox/file/{sandbox_id}/"
    origin = public_origin_from_request(request)
    return origin + path if origin else path


def sandbox_public_url(request: Request | None, path: str) -> str:
    """Absolute URL for same-origin sandbox paths (path must start with ``/``)."""
    if not path.startswith("/"):
        path = "/" + path
    origin = public_origin_from_request(request)
    return origin + path if origin else path


def _inject_iframe_base_href(html: str, sandbox_id: str, request: Request | None = None) -> str:
    """Inject static-file sandbox base href so remote viewers never rely on viewer-local localhost."""
    return inject_html_base_href(html, sandbox_static_base_href(sandbox_id, request))


def rewrite_loopback_location_header(location: str, upstream_port: int, path_prefix: str) -> str:
    """
    Map ``Location: http://127.0.0.1:{upstream_port}/…`` to same-origin ``path_prefix`` + path,
    so remote viewers do not navigate to their own loopback.
    """
    loc = (location or "").strip()
    if not loc:
        return location
    u = urlparse(loc)
    host = (u.hostname or "").lower()
    port = u.port
    if host in ("127.0.0.1", "localhost", "::1") and port == upstream_port:
        pp = path_prefix.rstrip("/")
        pth = u.path or "/"
        if pth == "/":
            new_path = pp + "/"
        else:
            new_path = pp + pth
        tail = (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")
        return new_path + tail
    return location


def rewrite_upstream_proxy_body(
    body: bytes,
    content_type: str | None,
    *,
    sandbox_id: str,
    proxy_kind: str,
    inject_backend_fetch_shim: bool,
    public_origin: str = "",
) -> tuple[bytes, bool]:
    """
    Rewrite compose/backend reverse-proxy bodies so loopback URLs stay on the factory origin.

    Returns ``(new_body, is_html)`` where ``is_html`` indicates CSP should be applied.
    """
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct == "text/html":
        text = body.decode("utf-8", errors="replace")
        text = _rewrite_localhost_urls(text)
        text = _rewrite_root_absolute_paths(text)
        text = _neutralize_iframe_breakouts(text)
        rel_prefix = (
            f"/api/sandbox/compose/{sandbox_id}/"
            if proxy_kind == "compose"
            else f"/api/sandbox/backend/{sandbox_id}/"
        )
        prefix = (
            public_origin.rstrip("/") + rel_prefix
            if public_origin
            else rel_prefix
        )
        text = inject_html_base_href(text, prefix)
        if inject_backend_fetch_shim:
            text = inject_preview_api_fetch_shim(text, sandbox_id)
        text = _inject_loopback_navigation_guard(text)
        return text.encode("utf-8"), True
    if ct in ("text/css", "application/javascript", "application/x-javascript", "text/javascript"):
        text = body.decode("utf-8", errors="replace")
        text = _rewrite_localhost_urls(text)
        text = _rewrite_root_absolute_paths(text)
        return text.encode("utf-8"), False
    return body, False


_NAV_GUARD_SCRIPT = r"""<script id="aicom-sandbox-loopback-guard">
(function(){
function blockedHost(h){
if(!h)return false;
var hn=String(h).toLowerCase();
if(hn.charAt(0)==='['&&hn.slice(-1)===']')hn=hn.slice(1,-1);
if(hn==='localhost'||hn==='127.0.0.1'||hn==='::1'||hn==='0.0.0.0')return true;
return hn.endsWith('.localhost');
}
function toRelative(u){
var p=u.pathname||'/';
return(p==='/'?'./':'.'+p)+u.search+u.hash;
}
document.addEventListener('click',function(e){
var el=e.target&&e.target.closest&&e.target.closest('a[href]');
if(!el)return;
var raw=el.getAttribute('href');
if(raw==null||raw===''||raw.trim().startsWith('#'))return;
if(/^mailto:|^tel:|^javascript:/i.test(raw.trim()))return;
try{
var u=new URL(raw.trim(),document.baseURI);
if(!/^https?:$/i.test(u.protocol))return;
if(blockedHost(u.hostname)){
e.preventDefault();e.stopPropagation();
window.location.href=toRelative(u);
}
}catch(x){}
},true);
})();
<\/script>"""


def _inject_loopback_navigation_guard(html: str) -> str:
    """Intercept clicks to loopback hosts so demos cannot escape preview to the viewer's machine."""
    if 'id="aicom-sandbox-loopback-guard"' in html:
        return html
    matches = list(re.finditer(r"</body\s*>", html, flags=re.I))
    if matches:
        pos = matches[-1].start()
        return html[:pos] + _NAV_GUARD_SCRIPT + html[pos:]
    return html + _NAV_GUARD_SCRIPT


# Smooth in-page jumps for marketing landings inside iframe (base href + long pages).
_SANDBOX_INPAGE_NAV_SNIPPET = """<style id="aicom-sandbox-nav-smooth">@media (prefers-reduced-motion: no-preference){html{scroll-behavior:smooth}}</style>
<script id="aicom-sandbox-hash-nav">
(function(){
document.addEventListener('click',function(e){
 var a=e.target&&e.target.closest&&e.target.closest('a[href]');
 if(!a)return;
 var raw=(a.getAttribute('href')||'').trim();
 if(!raw||raw==='#'||raw.charAt(0)!=='#')return;
 if(raw.indexOf('/',1)!==-1)return;
 var id;
 try{id=decodeURIComponent(raw.slice(1));}catch(x){id=raw.slice(1);}
 if(!id)return;
 var el=document.getElementById(id);
 if(!el)return;
 e.preventDefault();
 var reduce=0;
 try{reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches?1:0;}catch(x){}
 try{el.scrollIntoView({behavior:reduce?'auto':'smooth',block:'start'});}catch(x){el.scrollIntoView(true);}
 try{history.replaceState(null,'',raw);}catch(x){}
},true);
})();
</script>"""


def inject_sandbox_in_page_nav_helpers(html: str) -> str:
    """Ensure #section nav scrolls inside the iframe demo (single-page landings)."""
    if 'id="aicom-sandbox-hash-nav"' in html:
        return html
    matches = list(re.finditer(r"</body\s*>", html, flags=re.I))
    if matches:
        pos = matches[-1].start()
        return html[:pos] + _SANDBOX_INPAGE_NAV_SNIPPET + html[pos:]
    return html + _SANDBOX_INPAGE_NAV_SNIPPET


# CSP: keep navigations and form posts on our origin or HTTPS; block http://localhost etc.
# Shell page at ``/api/sandbox/view/{id}`` (sidebar + iframe). Must allow frame-src 'self'.
# iframe sandbox attribute for generated demo content (limits top-navigation / modals).
SANDBOX_IFRAME_SANDBOX_ATTR = (
    "allow-scripts allow-same-origin allow-forms allow-popups allow-downloads "
    "allow-modals allow-pointer-lock"
)

SANDBOX_VIEWER_CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "frame-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "base-uri 'self'; "
    "form-action 'none'; "
    "frame-ancestors 'self'; "
    "object-src 'none'; "
)

SANDBOX_HTML_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https:; "
    "script-src-attr 'none'; "
    "style-src 'self' 'unsafe-inline' https:; "
    "img-src 'self' data: https: blob:; "
    "font-src 'self' https: data:; "
    "connect-src 'self' https: wss:; "
    "media-src 'self' https: data:; "
    "worker-src 'self' blob:; "
    "frame-src 'self' https: data: blob:; "
    "object-src 'none'; "
    "form-action 'self' https:; "
    "base-uri 'self'; "
    "frame-ancestors 'self'; "
    "upgrade-insecure-requests; "
    # Allow HTTPS outbound links in marketing demos; block http://localhost (http not listed).
    "navigate-to 'self' https:"
)
