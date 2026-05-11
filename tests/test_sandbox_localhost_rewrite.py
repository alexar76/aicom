"""Sandbox preview: localhost URLs in generated demos must not escape the iframe."""

from web.backend.services import sandbox_static_rewrite as sb


def test_rewrite_localhost_with_port_and_query():
    s = 'src="http://127.0.0.1:5173/app.js?v=1"'
    assert sb._rewrite_localhost_urls(s) == 'src="./app.js?v=1"'


def test_rewrite_localhost_path_fragment():
    s = "navigate('http://localhost:8080/dashboard#alerts')"
    assert sb._rewrite_localhost_urls(s) == "navigate('./dashboard#alerts')"


def test_rewrite_localhost_root_only():
    assert sb._rewrite_localhost_urls('href="http://localhost:8080/"') == 'href="./"'


def test_rewrite_protocol_relative_localhost():
    assert sb._rewrite_localhost_urls('href="//localhost/faq"') == 'href="./faq"'
    assert sb._rewrite_localhost_urls("href='//127.0.0.1:3000/#pricing'") == "href='./#pricing'"


def test_rewrite_full_url_before_proto_relative_substring():
    """``http://localhost`` contains ``//localhost``; full-URL pass must run first."""
    assert sb._rewrite_localhost_urls('href="http://localhost/foo"') == 'href="./foo"'


def test_rewrite_ipv6_loopback():
    assert sb._rewrite_localhost_urls('href="http://[::1]:8080/x"') == 'href="./x"'
    assert sb._rewrite_localhost_urls('src="//[::1]/app.js"') == 'src="./app.js"'


def test_inject_loopback_guard_before_body_close():
    html = "<html><body><p>x</p></body></html>"
    out = sb._inject_loopback_navigation_guard(html)
    assert "aicom-sandbox-loopback-guard" in out
    assert out.find("</p>") < out.find("aicom-sandbox-loopback-guard")


def test_rewrite_root_absolute_href():
    s = '<a href="/pricing.html">Go</a>'
    out = sb._rewrite_root_absolute_paths(s)
    assert 'href="./pricing.html"' in out


def test_rewrite_root_absolute_preserves_protocol_relative():
    s = '<script src="//cdn.example.com/x.js"></script>'
    assert sb._rewrite_root_absolute_paths(s) == s


def test_neutralize_target_top():
    html = '<a href="./x" target="_top">x</a>'
    assert "target" not in sb._neutralize_iframe_breakouts(html).lower()


def test_inject_base_strips_conflicting_base_and_adds_api_base():
    html = '<html><head><base href="http://localhost:3000/"></head><body></body></html>'
    out = sb._inject_iframe_base_href(html, "sandbox-abc")
    assert "localhost" not in out.lower()
    assert 'href="/api/sandbox/file/sandbox-abc/"' in out
    assert out.lower().count("<base") == 1


def test_public_origin_from_host_header():
    class Req:
        headers = {"host": "5.129.212.122:9080"}
        url = type("U", (), {"scheme": "http"})()

    assert sb.public_origin_from_request(Req()) == "http://5.129.212.122:9080"


def test_public_origin_prefers_x_forwarded():
    class Req:
        headers = {
            "x-forwarded-proto": "https",
            "x-forwarded-host": "cdn.example.com, stale.example.com",
        }
        url = type("U", (), {"scheme": "http"})()

    assert sb.public_origin_from_request(Req()) == "https://cdn.example.com"


def test_sandbox_public_url_joins_origin():
    class Req:
        headers = {"host": "5.129.212.122:9080"}
        url = type("U", (), {"scheme": "http"})()

    assert (
        sb.sandbox_public_url(Req(), "/api/sandbox/file/x/index.html")
        == "http://5.129.212.122:9080/api/sandbox/file/x/index.html"
    )


def test_inject_base_href_absolute_when_request_has_host():
    class Req:
        headers = {"host": "5.129.212.122:9080"}
        url = type("U", (), {"scheme": "http"})()

    html = "<html><head></head><body></body></html>"
    out = sb._inject_iframe_base_href(html, "sandbox-abc", Req())
    assert 'href="http://5.129.212.122:9080/api/sandbox/file/sandbox-abc/"' in out


def test_rewrite_loopback_location_header():
    assert (
        sb.rewrite_loopback_location_header(
            "http://127.0.0.1:55123/dashboard?q=1",
            55123,
            "/api/sandbox/compose/sandbox-abc/",
        )
        == "/api/sandbox/compose/sandbox-abc/dashboard?q=1"
    )
    assert (
        sb.rewrite_loopback_location_header("http://127.0.0.1:55123/", 55123, "/api/sandbox/compose/x/")
        == "/api/sandbox/compose/x/"
    )
    assert (
        sb.rewrite_loopback_location_header("https://other.example/y", 55123, "/api/sandbox/compose/x/")
        == "https://other.example/y"
    )
