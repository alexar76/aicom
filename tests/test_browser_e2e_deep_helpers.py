"""Unit tests for browser deep-crawl URL helpers (no Playwright)."""

from web.backend.services.browser_e2e_deep import (
    deep_crawl_gate_issues,
    exception_in_product_output,
    is_loopback_href,
    normalize_visit_key,
    same_origin,
    spa_routes_from_source,
)


def test_same_origin_port():
    assert same_origin("http://127.0.0.1:9123/a.html", "http://127.0.0.1:9123/b.html")
    assert not same_origin("http://127.0.0.1:9123/a.html", "http://127.0.0.1:9124/a.html")


def test_normalize_visit_key_fragment():
    a = normalize_visit_key("http://127.0.0.1:5/page.html#faq")
    b = normalize_visit_key("http://127.0.0.1:5/page.html#pricing")
    assert a != b


def test_is_loopback_href():
    assert is_loopback_href("//localhost/foo")
    assert is_loopback_href("http://localhost:3000/")
    assert not is_loopback_href("./foo.html")
    assert not is_loopback_href("#faq")


def test_deep_crawl_gate_issues_http():
    issues = deep_crawl_gate_issues(
        {
            "navigation_failures": [],
            "loopback_hrefs": [],
            "pages": [{"url": "http://x/y", "status": 404}],
        }
    )
    assert any("deep_http_404" in i for i in issues)


def test_deep_crawl_flags_a_python_exception_painted_as_unknown():
    issues = deep_crawl_gate_issues(
        {
            "navigation_failures": [],
            "loopback_hrefs": [],
            "pages": [
                {
                    "url": "https://prod.vercel.app/",
                    "status": 200,
                    "text_snippet": (
                        "UNKNOWN AtlasClient.get_situation_brief() got an unexpected "
                        "keyword argument 'west'"
                    ),
                }
            ],
        }
    )
    assert any("deep_exception_in_ui" in i for i in issues)
    assert exception_in_product_output("got an unexpected keyword argument 'west'")


def test_spa_routes_are_read_from_react_router(tmp_path):
    """BFS over <a href> never left `/` on Sentinel. The operator console lives at
    /operator and is only declared in App.tsx, so spec_alignment_llm only ever saw
    the public widget."""
    src = tmp_path / "frontend" / "src"
    src.mkdir(parents=True)
    (src / "App.tsx").write_text(
        """
        <Routes>
          <Route path="/" element={<PublicWidget />} />
          <Route path="/login" element={<OperatorLogin />} />
          <Route path="/operator" element={<OperatorDashboard />} />
          <Route path="/analytics" element={<AnalyticsDashboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        """,
        encoding="utf-8",
    )
    routes = spa_routes_from_source(tmp_path)
    assert "/login" in routes
    assert "/operator" in routes
    assert "/analytics" in routes
    assert "/" not in routes


def test_api_401_is_an_auth_wall_not_a_missing_page():
    issues = deep_crawl_gate_issues(
        {
            "navigation_failures": [],
            "loopback_hrefs": [],
            "pages": [
                {
                    "url": "http://preview/api/analytics/dashboards",
                    "status": 401,
                    "text_snippet": '{"detail":"Unauthorized"}',
                }
            ],
        }
    )
    assert not any("deep_http_401" in i for i in issues), issues


def test_login_403_with_sign_in_copy_is_not_a_missing_page():
    issues = deep_crawl_gate_issues(
        {
            "navigation_failures": [],
            "loopback_hrefs": [],
            "pages": [
                {
                    "url": "http://preview/operator",
                    "status": 403,
                    "text_snippet": "Please sign in to continue",
                }
            ],
        }
    )
    assert not any("deep_http_403" in i for i in issues), issues


def test_http_404_still_fails_the_deep_crawl_gate():
    issues = deep_crawl_gate_issues(
        {
            "navigation_failures": [],
            "loopback_hrefs": [],
            "pages": [{"url": "http://preview/missing", "status": 404}],
        }
    )
    assert any("deep_http_404" in i for i in issues)


def test_e2e_credentials_match_the_sandbox_demo_identity(monkeypatch):
    monkeypatch.delenv("AIFACTORY_E2E_EMAIL", raising=False)
    monkeypatch.delenv("AIFACTORY_E2E_PASSWORD", raising=False)
    monkeypatch.delenv("AIFACTORY_E2E_USERNAME", raising=False)
    from core.demo_identity import sandbox_demo_email
    from web.backend.services.browser_e2e_deep import e2e_credentials

    creds = e2e_credentials()
    assert creds["email"] == sandbox_demo_email()
    assert creds["password"]
    assert creds["password"] != "e2e-password-change-me"
    assert "invalid" not in creds["email"]
