"""A publish gate that only checks the page certifies the part that cannot fail.

Measured on this product's first real publish. Vercel returned a URL, the HTML at `/` answered 200,
the pipeline logged "Vercel full-stack publish OK" and moved the product to SALES_ACTIVE. Every API
route answered:

    FUNCTION_INVOCATION_FAILED
    File "/var/task/api/app/utils/security.py", line 7, in <module>: import jwt
    ModuleNotFoundError: No module named 'jwt'

The HTML is static build output — Vercel serves it whether or not the Python function behind it can
be imported at all. So the one thing the gate looked at was the one thing a broken backend cannot
break.
"""

from __future__ import annotations

from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[1]
    / "web" / "backend" / "services" / "auto_publish.py"
).read_text(encoding="utf-8")


def test_the_verifier_exists_and_probes_real_api_paths():
    body = SRC[SRC.index("def verify_published_api(") : SRC.index("def _merge_publish_record(")]
    for path in ("/api/health", "/openapi.json"):
        assert path in body, f"the probe never tries {path}"


def test_a_function_crash_page_is_not_success():
    """Vercel answers 500 with an HTML error page; a naive "did it respond" check passes on it."""
    body = SRC[SRC.index("def verify_published_api(") : SRC.index("def _merge_publish_record(")]
    assert "FUNCTION_INVOCATION_FAILED" in body
    assert "A server error has occurred" in body


def test_a_404_counts_as_a_living_backend():
    """404 means the app answered and has no such route — the import worked, which is the point."""
    body = SRC[SRC.index("def verify_published_api(") : SRC.index("def _merge_publish_record(")]
    assert "200 <= status < 500" in body


def test_a_dead_api_stops_the_publish_being_recorded():
    tail = SRC[SRC.index("api_health = verify_published_api(url)") :]
    assert 'if ok and api_health and not api_health.get("api_ok"):' in tail
    assert "ok = False" in tail
    assert "is not being recorded as published" in tail


def test_the_success_line_carries_the_proof():
    tail = SRC[SRC.index("api_health = verify_published_api(url)") :]
    assert 'api_health.get("proof")' in tail, "a success message with no evidence is the old bug"
