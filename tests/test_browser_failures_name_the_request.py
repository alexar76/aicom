"""A 500 in the console is not a finding until it says which request failed.

The browser gate reported, verbatim and nothing more:

    console_error: Failed to load resource: the server responded with a status of 500 (Internal
    Server Error)

No method, no path, no file. This exact shape has misdirected four rounds on this product: two
guessing in App.tsx at a 500, and two more at the 405 costume of the same bug — which turned out to
be an API route shadowing the SPA catch-all, nowhere near the frontend. Playwright knows the method,
the path and the status; nobody was listening to the response event.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "web" / "backend" / "services" / "browser_preview_e2e.py").read_text(encoding="utf-8")


def test_failing_responses_are_captured():
    assert 'page.on("response", on_response)' in SRC
    capture = SRC[SRC.index("def on_response(") :][:1400]
    assert "if status < 400:" in capture, "only failures are worth recording"
    for field in ('"method"', '"path"', '"status"', '"url"'):
        assert field in capture, f"the capture drops {field}"


def test_each_failure_becomes_an_issue_naming_method_path_and_status():
    block = SRC[SRC.index("_seen_failures: set") :][:1800]
    assert "browser_http_" in block
    assert "fr['method']" in block and "fr['path']" in block and "fr['status']" in block
    assert "route_handler_file" in block, "the finding should name the file that serves the route"
    assert "_seen_failures" in block, "one issue per distinct failure, not per repeated request"


def test_the_pathless_console_error_is_annotated_with_the_real_paths():
    """Kept as well as the new finding: the console error is what a human sees in devtools, and
    the annotation is what makes it actionable without cross-referencing."""
    block = SRC[SRC.index("# Strict: any console.error from scripts") :][:900]
    assert '"Failed to load resource" in t' in block
    assert "the failing request(s) this round" in block


def test_the_report_carries_the_failures_for_downstream_consumers():
    assert '"failed_requests": failed_requests[:20],' in SRC


def test_a_failure_fails_the_gate():
    block = SRC[SRC.index("_seen_failures: set") :][:1200]
    assert "passed = False" in block


def test_browser_findings_reach_the_repair_scope():
    """A finding that names a file it cannot be scoped to is still unfixable.

    The same lesson as the tokenless login: the round fixed auth.py, the scope named only the
    static finding's file, and the out-of-scope guard reverted the completed fix as free. Runtime
    observers — the journey and the browser — both have to feed the scope.
    """
    qa = (ROOT / "agents" / "qa.py").read_text(encoding="utf-8")
    block = qa[qa.index("_runtime_lines") :][:700]
    assert 'journey.get("issues")' in block
    assert 'browser_e2e or {}).get("issues")' in block
    assert "_journey_issue_file(" in block
    assert "blocking_files.append(_jf)" in block
