"""The Vulnetix-class scanner (scripts/vulnetix_class_scan.py): each rule fires on the shape a bug had before its fix
commit and stays quiet on the shape the fix left. The snippets are reduced from the real files; the last test checks
the real files at the real commits when the history is in the checkout."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import vulnetix_class_scan as vx  # noqa: E402


def rules(source: str, path: str = "pkg/mod.py") -> list[str]:
    return sorted({f.rule for f in vx.scan_file(path, textwrap.dedent(source))})


# --- VX-FWD-HEADER-TRUST (oracle_core client_key before 5ad17c13a) -------------------------------------------------

def test_forwarding_header_read_without_peer_check_fires():
    assert rules('''
        def client_key(request):
            xri = (request.headers.get("x-real-ip") or "").strip()
            if xri:
                return xri
            return request.client.host if request.client else "*"
    ''') == ["VX-FWD-HEADER-TRUST"]


@pytest.mark.parametrize("fixed", [
    # oracle_core after: headers only inside the trusted-proxy branch
    '''
    def client_key(request):
        peer = request.client.host if request.client else ""
        if peer_is_local_proxy(peer):
            xri = (request.headers.get("x-real-ip") or "").strip()
            if xri:
                return xri
        return peer or "*"
    ''',
    # logos after: early return for a direct caller
    '''
    def _client_key(request):
        peer = request.client.host if request.client else ""
        if not _from_local_proxy(peer):
            return peer or "unknown"
        return (request.headers.get("x-real-ip") or "").strip()
    ''',
    # basanos / kova after: conditional expression
    '''
    def _peer(request):
        peer = request.client.host if request.client else ""
        real = (request.headers.get("x-real-ip") or "").strip() if _from_local_proxy(peer) else ""
        return real or peer
    ''',
    # hub / lottery / charon: membership in the trusted proxies
    '''
    def _client_address(request, trusted_proxies):
        peer = str(request.client.host)
        if not peer or peer not in trusted_proxies:
            return peer
        raw = request.headers.get("x-forwarded-for") or ""
        return raw.split(",")[-1].strip() or peer
    ''',
    # desk kernel: read first, used only together with the peer check
    '''
    def client_ip(request):
        peer = request.client.host if request.client else ""
        chain = [p.strip() for p in (request.headers.get("x-forwarded-for") or "").split(",") if p.strip()]
        if chain and _from_local_proxy(peer):
            return chain[-1]
        return peer
    ''',
    # metis local_caller: only asks whether the header is present, to refuse
    '''
    def local_caller(request):
        return not any(h in request.headers for h in ("x-forwarded-for", "x-real-ip"))
    ''',
])
def test_forwarding_header_behind_a_peer_check_is_quiet(fixed):
    assert rules(fixed) == []


# --- VX-306-OPEN-WITHOUT-KEY (platon, metis before 5ad17c13a) ------------------------------------------------------

def test_auth_check_that_admits_everyone_without_a_key_fires():
    assert rules('''
        def _write_authorized(token):
            steer_token = _steer_token()
            if not steer_token:
                prod = os.environ.get("AIFACTORY_PROD") == "1"
                if prod:
                    return False
                return True
            return hmac.compare_digest(token or "", steer_token)
    ''') == ["VX-306-OPEN-WITHOUT-KEY"]
    assert rules('''
        async def verify_api_key(credentials=None):
            expected = get_api_key_from_env()
            if not production and not expected:
                logger.warning("serving unauthenticated")
                return None
            check(credentials, expected)
    ''') == ["VX-306-OPEN-WITHOUT-KEY"]


@pytest.mark.parametrize("fixed", [
    '''
    async def verify_api_key(request, credentials=None):
        expected = get_api_key_from_env()
        if not production and not expected:
            if not local_caller(request):
                raise HTTPException(401)
            return None
        check(credentials, expected)
    ''',
    # a failed password check returns None = refused, not admitted
    '''
    def authenticate_customer(email, password):
        customer = find(email)
        if not pwd_context.verify(password, customer["password_hash"]):
            return None
        return customer
    ''',
])
def test_auth_check_limited_to_local_callers_is_quiet(fixed):
    assert rules(fixed) == []


# --- VX-918-CHECK-THEN-CONNECT (atlas, emberline, hestia before 5ad17c13a) ------------------------------------------

@pytest.mark.parametrize("bad", [
    '''
    async def deliver(self, url, body):
        refusal = await _non_public_resolution(url)
        if refusal:
            return
        async with httpx.AsyncClient() as client:
            await client.post(url, content=body)
    ''',
    '''
    def send(url, payload):
        assert_safe_webhook_url(url)
        with httpx.Client(timeout=8.0) as client:
            client.post(url, json=payload)
    ''',
    '''
    def proof(domain):
        require_public(domain)
        with httpx.Client() as client:
            with client.stream("GET", f"https://{domain}/.well-known/proof") as res:
                return res.read()
    ''',
])
def test_check_then_request_by_name_fires(bad):
    assert rules(bad) == ["VX-918-CHECK-THEN-CONNECT"]


@pytest.mark.parametrize("fixed", [
    # pinned: the request goes to the checked address
    '''
    async def deliver(self, url, body):
        target, headers, ext = pin_target(url)
        async with httpx.AsyncClient() as client:
            await client.post(target, content=body, headers=headers, extensions=ext)
    ''',
    # a check that only warns is not a guard (hub doctor)
    '''
    def doctor(url):
        if not _public_host(url):
            print("not public")
        httpx.get(f"{url}/.well-known/ai-market.json")
    ''',
    # dict lookups are not requests
    '''
    def validate(self, role):
        if not is_public(role):
            return
        return self.modules.get(role)
    ''',
])
def test_pinned_or_unrelated_is_quiet(fixed):
    assert rules(fixed) == []


# --- a second, unchecked lookup after the check (three MOMUS-loop "fixes", 2026-11-16) ---------------------------------

@pytest.mark.parametrize("bad", [
    # metis branch 5f53ba28: getaddrinfo in the same function, connect to its first answer
    """
    async def run(self, url):
        try:
            validate_url(url, allowed_schemes={"http", "https"})
        except ValueError:
            return None
        parsed = urlparse(url)
        host = parsed.hostname or ""
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        pinned_ip = infos[0][4][0]
        pinned_url = f"{parsed.scheme}://{pinned_ip}{parsed.path}"
        async with httpx.AsyncClient() as client:
            return await client.post(pinned_url, json={}, headers={"Host": host})
    """,
    # web branches: the lookup in a helper; `if not infos: raise` checks that there is an answer, not which
    """
    def _resolve_pinned_host(url):
        parsed = urlparse(url)
        infos = socket.getaddrinfo(parsed.hostname or "", parsed.port or 443, type=socket.SOCK_STREAM)
        if not infos:
            raise ValueError("no answer")
        return parsed.scheme, infos[0][4][0], parsed.port or 443

    async def search_v2(intent):
        fed_url = _federation_hub_url()
        if not _federation_url_is_safe(fed_url):
            return {}
        try:
            scheme, pinned_ip, port = _resolve_pinned_host(fed_url)
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{scheme}://{pinned_ip}:{port}/ai-market/v2/search")
        except Exception:
            return {}
    """,
])
def test_a_second_unchecked_lookup_after_the_check_fires(bad):
    assert rules(bad) == ["VX-918-CHECK-THEN-CONNECT"]


@pytest.mark.parametrize("fixed", [
    # ATLAS delivery after 5ad17c13a: every answer checked, the URL carries an address that passed
    """
    async def _delivery_target(url):
        parts = urlsplit(url)
        host = parts.hostname or ""
        infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addrs = list(dict.fromkeys(info[4][0] for info in infos))
        bad = [a for a in addrs if not _is_public(a)]
        if bad or not addrs:
            return "refused", "", {}, {}
        return "", urlunsplit((parts.scheme, addrs[0], parts.path, parts.query, "")), {"Host": host}, {"sni_hostname": host}

    async def deliver(url):
        if not url_is_safe(url):
            return
        refusal, target, headers, ext = await _delivery_target(url)
        if refusal:
            return
        async with httpx.AsyncClient() as client:
            await client.post(target, headers=headers, extensions=ext)
    """,
    # the lookup's answer checked in place before the connect
    """
    async def fetch(url):
        if not check_url(url):
            return None
        host = urlsplit(url).hostname
        ip = socket.gethostbyname(host)
        if not ipaddress.ip_address(ip).is_global:
            raise ValueError("private")
        async with httpx.AsyncClient() as client:
            return await client.get(f"https://{ip}/x", headers={"Host": host}, extensions={"sni_hostname": host})
    """,
    # a lookup with no check before it is not this rule (there is nothing to bypass)
    """
    async def ping(url):
        host = urlsplit(url).hostname
        ip = socket.gethostbyname(host)
        async with httpx.AsyncClient() as client:
            return await client.get(f"http://{ip}/health")
    """,
])
def test_a_lookup_whose_answer_is_checked_is_quiet(fixed):
    assert rules(fixed) == []


def test_pin_helper_that_lets_https_through_unpinned_fires():
    bad = '''
        def pin_target(url):
            parsed = urlparse(url)
            if parsed.scheme != "http" or not parsed.hostname:
                return url, {}
            return pinned(parsed), {"Host": parsed.netloc}
    '''
    fixed = '''
        def pin_target(url):
            parsed = urlparse(url)
            if not parsed.hostname:
                return url, {}, {}
            return pinned(parsed), {"Host": parsed.netloc}, {"sni_hostname": parsed.hostname}
    '''
    assert rules(bad) == ["VX-918-UNPINNED-RETURN"]
    assert rules(fixed) == []


# --- VX-SSH-NO-HOSTKEY (skopos git push before 5ad17c13a) ----------------------------------------------------------

def test_ssh_without_host_key_check_fires_in_code_and_scripts():
    assert rules('''
        ssh = "ssh -i key -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    ''') == ["VX-SSH-NO-HOSTKEY"]
    assert rules("ssh -o StrictHostKeyChecking=no host true\n", "scripts/deploy.sh") == ["VX-SSH-NO-HOSTKEY"]


def test_ssh_exception_for_a_local_remote_or_in_prose_is_quiet():
    assert rules('''
        """Never use StrictHostKeyChecking=no for a remote host."""
        if ssh_remote_is_local(url):
            checking = "-o StrictHostKeyChecking=no"
    ''') == []


# --- acceptance and diffing -----------------------------------------------------------------------------------------

def test_vx_ok_needs_a_reason():
    with_reason = '''
        def k(request):
            # vx-ok: test-only helper, never mounted
            return request.headers.get("x-real-ip")
    '''
    empty = with_reason.replace("test-only helper, never mounted", "")
    assert rules(with_reason) == []
    assert rules(empty) == ["VX-FWD-HEADER-TRUST"]


def test_tests_docs_and_artifacts_are_not_scanned():
    bad = 'def k(request):\n    return request.headers.get("x-real-ip")\n'
    for path in ("tests/test_x.py", "pkg/tests/helpers.py", "artifacts/x/app.py", "docs/a.py", "pkg/test_app.py"):
        assert vx.scan_file(path, bad) == []


def test_finding_key_ignores_line_numbers():
    a = vx.scan_file("p.py", 'def k(request):\n    return request.headers.get("x-real-ip")\n')[0]
    b = vx.scan_file("p.py", '\n\n\ndef k(request):\n    return request.headers.get("x-real-ip")\n')[0]
    assert a.line != b.line and a.key == b.key


# --- the real files at the real commits ----------------------------------------------------------------------------

HISTORY = [
    ("5ad17c13a", "oracles/core/oracle_core/app.py", "VX-FWD-HEADER-TRUST"),
    ("5ad17c13a", "logos/logos/app.py", "VX-FWD-HEADER-TRUST"),
    ("5ad17c13a", "platon/backend/platon/main.py", "VX-306-OPEN-WITHOUT-KEY"),
    ("5ad17c13a", "metis/metis/api/auth.py", "VX-306-OPEN-WITHOUT-KEY"),
    ("5ad17c13a", "atlas/atlas/delivery.py", "VX-918-CHECK-THEN-CONNECT"),
    ("5ad17c13a", "cite-desks/emberline/backend/app/alerts.py", "VX-918-CHECK-THEN-CONNECT"),
    ("5ad17c13a", "hestia/hestia/domains.py", "VX-918-CHECK-THEN-CONNECT"),
    ("5ad17c13a", "aimarket-mcp/aimarket_mcp/security.py", "VX-918-UNPINNED-RETURN"),
    ("5ad17c13a", "alien-monitor/backend/hub_discovery.py", "VX-918-UNPINNED-RETURN"),
    ("5ad17c13a", "skopos/skopos/remediation/git_push.py", "VX-SSH-NO-HOSTKEY"),
    ("5ad17c13a", "independent/kova-gateway/backend/kova/app.py", "VX-FWD-HEADER-TRUST"),
    ("5ad17c13a", "basanos/agent.py", "VX-FWD-HEADER-TRUST"),
    ("5ad17c13a", "cite-desks/kernel/desk_kernel/service/security.py", "VX-FWD-HEADER-TRUST"),
]


def _at(ref: str, path: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


@pytest.mark.parametrize("commit,path,rule", HISTORY)
def test_real_vulnetix_fix_commits_before_and_after(commit, path, rule):
    before, after = _at(f"{commit}^", path), _at(commit, path)
    if before is None or after is None:
        pytest.skip("history not in this checkout (shallow clone)")
    assert rule in {f.rule for f in vx.scan_file(path, before)}
    assert not [f for f in vx.scan_file(path, after) if f.rule == rule]


# --- Rules added 2026-11-16 from outside code (artifacts/momus-outside-cves-2026-11-16) ------------------------------

def test_tls_verification_off_fires_and_config_flag_does_not():
    assert "VX-295-TLS-OFF" in rules('''
        import requests
        def pull(url):
            return requests.get(url, verify=False, timeout=5)
    ''')
    assert "VX-295-TLS-OFF" in rules('''
        import ssl
        def ctx():
            c = ssl.create_default_context()
            c.check_hostname = False
            c.verify_mode = ssl.CERT_NONE
            return c
    ''')
    assert "VX-295-TLS-OFF" not in rules('''
        import requests
        def pull(url, verify_tls):
            return requests.get(url, verify=verify_tls, timeout=5)
    ''')


def test_tls_relaxed_for_a_loopback_relay_or_a_pinned_certificate_is_accepted():
    assert "VX-295-TLS-OFF" not in rules('''
        import ssl
        def deliver(host):
            c = ssl.create_default_context()
            if is_loopback(host):
                c.check_hostname = False
                c.verify_mode = ssl.CERT_NONE
            return c
    ''')
    assert "VX-295-TLS-OFF" not in rules('''
        import ssl
        def pinned_request(host, fingerprint):
            c = ssl.create_default_context()
            c.check_hostname = False
            c.verify_mode = ssl.CERT_NONE
            sock = c.wrap_socket(raw)
            assert sha256(sock.getpeercert(True)) == fingerprint
    ''')


def test_js_tls_off_fires():
    assert rules("const agent = new https.Agent({ rejectUnauthorized: false });\n", "src/client.ts") == ["VX-295-TLS-OFF"]
    assert rules("const agent = new https.Agent({ rejectUnauthorized: true });\n", "src/client.ts") == []


def test_tool_fetching_the_callers_url_unchecked_fires_and_a_checked_one_does_not():
    assert "VX-918-FETCH-UNCHECKED" in rules('''
        import requests
        class ScrapeWebsiteTool(BaseTool):
            def _run(self, website_url: str):
                page = requests.get(website_url, timeout=15)
                return page.text
    ''')
    assert "VX-918-FETCH-UNCHECKED" not in rules('''
        import requests
        class ScrapeWebsiteTool(BaseTool):
            def _run(self, website_url: str):
                validate_url(website_url)
                page = requests.get(website_url, timeout=15, allow_redirects=False)
                return page.text
    ''')
    # A helper that is not an entry point is not judged: its URLs are usually the operator's own.
    assert "VX-918-FETCH-UNCHECKED" not in rules('''
        import urllib.request
        def _get(url):
            return urllib.request.urlopen(url, timeout=5).read()
    ''')


def test_redirect_followed_after_the_address_check_fires():
    assert "VX-918-REDIRECT-AFTER-CHECK" in rules('''
        import requests
        def fetch(url):
            if not is_safe_url(url):
                raise ValueError(url)
            return requests.get(url, timeout=10).text
    ''')
    assert "VX-918-REDIRECT-AFTER-CHECK" not in rules('''
        import requests
        def fetch(url):
            if not is_safe_url(url):
                raise ValueError(url)
            return requests.get(url, timeout=10, allow_redirects=False).text
    ''')
    # base64's url-safe helpers are not an address check
    assert "VX-918-REDIRECT-AFTER-CHECK" not in rules('''
        import base64, urllib.request
        def post(name, endpoint):
            att = base64.urlsafe_b64encode(name.encode())
            req = urllib.request.Request(endpoint, data=att)
            return urllib.request.urlopen(req)
    ''')


def test_write_route_on_an_app_with_no_auth_fires_and_a_router_is_not_judged():
    assert "VX-306-ROUTE-NO-AUTH" in rules('''
        from fastapi import FastAPI
        app = FastAPI()
        @app.post("/runs")
        def create_run(body: dict):
            return queue.put(body)
    ''')
    assert "VX-306-ROUTE-NO-AUTH" not in rules('''
        from fastapi import FastAPI, Depends
        app = FastAPI()
        @app.post("/runs")
        def create_run(body: dict, user=Depends(current_user)):
            return queue.put(body)
    ''')
    assert "VX-306-ROUTE-NO-AUTH" not in rules('''
        from fastapi import APIRouter
        router = APIRouter()
        @router.post("/runs")
        def create_run(body: dict):
            return queue.put(body)
    ''')
