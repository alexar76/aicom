"""index.html is `<div id="root">`. Scoring it produced demo_quality F / 28.

ux_structure_thin, ux_missing_cta, visual_insufficient_design_tokens and
visual_no_media_queries all fired while PublicWidget.tsx already had a heading
and a button and frontend/src/styles/index.css already had :root tokens and
@media rules the gate never opened.
"""

from web.backend.services.demo_quality import assess_product_demo, quality_gates_pass


def test_a_vite_shell_is_judged_by_the_react_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_VISUAL_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_VISUAL_QUALITY_APP_CHECKS", "1")
    pid = "prod-spa-shell"
    code = tmp_path / "code" / pid
    (code / "frontend" / "src" / "pages").mkdir(parents=True)
    (code / "frontend" / "src" / "styles").mkdir(parents=True)
    (code / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">'
        "<title>Sentinel</title></head><body><div id=\"root\"></div>"
        '<script type="module" src="./src/main.tsx"></script></body></html>',
        encoding="utf-8",
    )
    (code / "frontend" / "src" / "styles" / "index.css").write_text(
        """
        :root { --bg: #0a0f14; --text: #e8eef2; --accent: #00d4aa; }
        @media (max-width: 640px) { body { padding: 8px; } }
        :focus-visible { outline: 2px solid var(--accent); }
        """,
        encoding="utf-8",
    )
    (code / "frontend" / "src" / "pages" / "PublicWidget.tsx").write_text(
        """
        export default function PublicWidget() {
          return (
            <main>
              <section>
                <h1>Sentinel</h1>
                <p>Verified safety companion with evidence receipts.</p>
                <button>Get Safety Status</button>
                <div className="skeleton" aria-busy="true">loading</div>
                <div className="empty-state">nothing yet</div>
                <div role="alert">error-state</div>
                <div aria-live="polite" className="toast">saved</div>
              </section>
            </main>
          );
        }
        """,
        encoding="utf-8",
    )
    spec = {
        "delivery_profile": "full_software",
        "description": "Sentinel verified safety companion with evidence receipts",
        "core_features": [{"name": "Safety status", "description": "evidence receipts"}],
    }
    rep = assess_product_demo(pid, spec, data_root=str(tmp_path))
    codes = {i.get("code") for i in rep["issues"]}
    assert "ux_structure_thin" not in codes, codes
    assert "ux_missing_cta" not in codes, codes
    assert "visual_insufficient_design_tokens" not in codes, codes
    assert "visual_no_media_queries" not in codes, codes
    assert "visual_app_missing_skeleton" not in codes, codes
    assert "root_absolute_paths" not in codes, codes
    assert rep["score"] >= 55
    assert quality_gates_pass(rep, delivery_profile="full_software") is True


def test_vite_src_entry_is_not_a_sandbox_breaker(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_VISUAL_QUALITY_GATE", "0")
    pid = "prod-vite-abs"
    code = tmp_path / "code" / pid
    (code / "frontend" / "src" / "pages").mkdir(parents=True)
    (code / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">'
        "<title>Sentinel</title></head><body><div id=\"root\"></div>"
        '<script type="module" src="/src/main.tsx"></script>'
        '<link rel="stylesheet" href="/assets/index-abc.css">'
        "</body></html>",
        encoding="utf-8",
    )
    (code / "frontend" / "src" / "pages" / "PublicWidget.tsx").write_text(
        "<main><section><h1>Sentinel</h1><button>Get Safety Status</button></section></main>",
        encoding="utf-8",
    )
    spec = {
        "delivery_profile": "full_software",
        "description": "Sentinel verified safety companion with evidence receipts",
        "core_features": [{"name": "Safety status", "description": "evidence receipts"}],
    }
    rep = assess_product_demo(pid, spec, data_root=str(tmp_path))
    codes = {i.get("code") for i in rep["issues"]}
    assert "root_absolute_paths" not in codes, codes


def test_non_bundler_root_href_still_fails():
    from web.backend.services.demo_quality import _root_absolute_sandbox_breakers

    assert _root_absolute_sandbox_breakers('<a href="/docs/manual.html">docs</a>')
    assert not _root_absolute_sandbox_breakers('<script src="/src/main.tsx"></script>')


def test_spec_coverage_counts_tokens_not_whole_pm_sentences():
    """Sentinel sat at 8% because the spec said 'embeddable safety widget' and the
    heading said 'Sentinel' + 'Get Safety Status'. Whole-phrase matching cannot pass."""
    from web.backend.services.demo_quality import _coverage_score

    ui = "<h1>sentinel</h1> get safety status evidence receipts operator dashboard atlas"
    kws = [
        "embeddable safety widget",
        "a single script tag that renders a location-aware safety badge",
        "atlas capability invokes",
        "operator console with evidence receipts",
        "this exact unused phrase never appears anywhere in the tree xyzzyplugh",
    ]
    cov = _coverage_score(ui, kws)
    assert cov >= 40, cov
    assert cov < 100, cov


def test_hover_border_color_is_not_read_as_text_color():
    """Sentinel's leftover autofix hover set background-color and border-color to the same
    teal. ``\\bcolor`` matched inside ``border-color``, so fg==bg and ratio 1.0 failed
    the critical CTA gate while the resting button was dark-on-teal (~10:1)."""
    from web.backend.services.demo_quality import _extract_foreground_rgb, _has_low_contrast_cta

    hover_only = "background-color: #00e5bb !important; border-color: #00e5bb !important;"
    assert _extract_foreground_rgb(hover_only) is None
    css = """
    button, .btn, .button, [class*="button"] {
      color: #0a0f14 !important;
      background-color: #00d4aa !important;
      border: 1px solid #00d4aa !important;
    }
    button:hover, .btn:hover, .button:hover, [class*="button"]:hover {
      background-color: #00e5bb !important;
      border-color: #00e5bb !important;
    }
    """
    assert _has_low_contrast_cta("", css) is False
    pale = ".btn { background-color: #22c55e; color: #d1d5db; }"
    assert _has_low_contrast_cta("", pale) is True