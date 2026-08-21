"""The last word on a deployment belongs to a browser pointed at the deployed URL.

Every other gate measures a sandbox — uvicorn on loopback, a venv built for the run, a preview build
served from disk. That is where two defects hid on a product that passed nine gates and published:

* `import jwt` resolved in the preview venv (PyJWT was installed there transitively) and did not
  exist in the deployed function — every API route answered FUNCTION_INVOCATION_FAILED;
* 47 Tailwind utility classes styled nothing, because the product had no Tailwind — 9 of 31 elements
  on the live page carried any non-default styling, and it looked like an unstyled document.

Both were obvious in two seconds to the person who opened the link. Measured against the real
deployment, this gate reports: passed=False, api=False, styled_ratio=0.29.

The first version of this gate passed that same URL, which is worth recording: the page load touched
no API (the product waits for input), and a bare count of styled elements cleared a lenient
threshold. A gate that only watches what a page does on load certifies nothing about a product that
does something when you press its button.

The next hole: clicking Get Safety Status on empty required lat/lon. HTML5 validation swallowed
the click, /api/health was 200, and the visitor still saw
`AtlasClient.get_situation_brief() got an unexpected keyword argument 'west'`.
"""

from __future__ import annotations

from pathlib import Path

from web.backend.services.browser_e2e_deep import exception_in_product_output
from web.backend.services.live_deployment_gate import _repair_scope_from_issues, _sweep_live_api

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "web" / "backend" / "services" / "live_deployment_gate.py").read_text(encoding="utf-8")
PUBLISH = (ROOT / "web" / "backend" / "services" / "auto_publish.py").read_text(encoding="utf-8")
EXECUTOR = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
DEEP = (ROOT / "web" / "backend" / "services" / "browser_e2e_deep.py").read_text(encoding="utf-8")


def test_the_api_is_probed_even_when_the_page_never_calls_it():
    """The exact hole in the first version: a dead backend behind a page that loads no data."""
    assert "api_paths = (" in GATE
    assert "/api/health" in GATE and "/openapi.json" in GATE
    assert "live_api_dead:" in GATE
    assert "FUNCTION_INVOCATION_FAILED" in GATE, "the crash page must not read as a live response"


def test_styling_is_judged_as_a_ratio_not_a_count():
    """9 styled elements passed a count-based threshold on a page that was visibly unstyled."""
    assert "_MIN_STYLED_RATIO" in GATE
    assert "styled_ratio" in GATE
    assert "_MIN_STYLED_ELEMENTS" not in GATE, "the count threshold is what let the failure through"


def test_color_and_font_count_as_paint_on_a_compact_widget():
    """Sentinel's live page had 15 elements, 6 with padding/flex (40%), and an h1.
    The gate wanted 45%. The missing 5% was `color: var(--text)` / Inter on the rest."""
    assert "cs.color" in GATE
    assert "fontFamily" in GATE


def test_the_gate_runs_full_ui_not_a_single_empty_click():
    """Clicking the primary button on an empty required form certifies nothing.

    Sentinel's lat/lon inputs are required. The click never submitted. The TypeError behind
    Get Safety Status never ran. The gate still passed.
    """
    assert "run_deep_crawl" in GATE
    assert "spa_routes_from_source" in GATE
    assert "_sweep_live_api" in GATE
    assert "/api/advisory" in GATE
    assert "52.52" in GATE and "13.40" in GATE
    assert "live_exception_in_ui" in GATE


def test_forms_are_filled_before_buttons_are_clicked():
    """Order used to be click then fill: HTML5 validation ate the click."""
    fill_at = DEEP.index("_fill_and_submit_forms")
    click_at = DEEP.index("_click_misc_controls")
    assert fill_at < click_at
    assert 'el.fill("52.52"' in DEEP
    assert 'el.fill("13.40"' in DEEP


def test_deployed_5xx_findings_say_they_are_production():
    """A repair round has to know this is not the sandbox, or it will look for the defect locally
    and find nothing — the sandbox is where the code works."""
    assert "on the DEPLOYED site" in GATE
    assert "preview venv" in GATE


def test_an_unavailable_browser_skips_rather_than_fails():
    """No Playwright is not evidence of a broken deployment — unless the HTTP sweep already
    found a Python exception in a 200. Then the gate must fail without a browser."""
    assert 'out["skipped"] = True' in GATE
    assert "playwright_unavailable" in GATE
    assert "if issues:" in GATE


def test_publication_is_not_recorded_when_the_live_gate_fails():
    tail = PUBLISH[PUBLISH.index("live_gate: dict[str, Any] = {}") :]
    assert 'if not live_gate.get("skipped") and not live_gate.get("passed"):' in tail
    assert "ok = False" in tail
    assert "recorded as published" in tail


def test_the_gate_runs_after_the_deployment_exists():
    """Pointing a browser at a URL that has not been created yet proves nothing."""
    assert PUBLISH.index("live_gate: dict[str, Any] = {}") > PUBLISH.index("reachability = verify_published_url(url)")


def test_the_findings_are_persisted_for_the_repair_round():
    assert '"live_gate": live_gate' in PUBLISH
    assert "product_id=product_id" in PUBLISH


def test_a_failed_live_gate_returns_the_product_to_dev_fixing():
    """DevOps used to record ok=False and then walk to SALES_ACTIVE anyway."""
    assert "live_gate_failed" in EXECUTOR
    assert 'reason="live_deployment_gate"' in EXECUTOR
    assert "live_gate_blocked" in EXECUTOR
    assert "BUG_FOUND → developer DEV_FIXING (full UI of the deployed site)" in EXECUTOR


def test_sentinel_typeerror_is_an_exception_in_the_ui():
    reason = (
        "ATLAS sensor mesh unavailable: AtlasClient.get_situation_brief() "
        "got an unexpected keyword argument 'west'"
    )
    hit = exception_in_product_output(reason)
    assert hit
    assert "unexpected keyword argument" in hit.lower()
    assert not exception_in_product_output("Insufficient sensor data for this location")
    assert not exception_in_product_output('{"level":"UNKNOWN","reason":"mesh refused: quota"}')


def test_repair_scope_names_the_atlas_files(tmp_path):
    code = tmp_path / "code"
    (code / "backend" / "app" / "services").mkdir(parents=True)
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "services" / "atlas_client.py").write_text(
        "class AtlasClient:\n    async def get_situation_brief(self, lat, lon):\n        return {}\n",
        encoding="utf-8",
    )
    (code / "backend" / "app" / "routers" / "advisory.py").write_text(
        "async def get_advisory():\n    return await atlas.get_situation_brief(west=1)\n",
        encoding="utf-8",
    )
    scope = _repair_scope_from_issues(
        [
            "live_exception_in_ui:/api/advisory:200: AtlasClient.get_situation_brief() "
            "got an unexpected keyword argument 'west'"
        ],
        code,
    )
    assert any(p.endswith("atlas_client.py") for p in scope)
    assert any(p.endswith("advisory.py") for p in scope)


def test_repair_scope_names_auth_seed_on_demo_auth_401(tmp_path):
    code = tmp_path / "code"
    (code / "backend" / "app" / "routers").mkdir(parents=True)
    (code / "backend" / "app" / "services").mkdir(parents=True)
    (code / "backend" / "app" / "routers" / "auth.py").write_text(
        "def login():\n    return {}\n",
        encoding="utf-8",
    )
    (code / "backend" / "app" / "services" / "demo_seed.py").write_text(
        'email = os.getenv("SANDBOX_DEMO_EMAIL")\n',
        encoding="utf-8",
    )
    scope = _repair_scope_from_issues(
        [
            "live_demo_auth_mismatch:POST /api/auth/login:401 on the DEPLOYED site. "
            "Factory live-gate credentials were rejected."
        ],
        code,
    )
    assert any(p.endswith("auth.py") for p in scope)
    assert any("demo_seed" in p for p in scope)


def test_demo_auth_issue_text_does_not_blame_missing_dependency():
    from web.backend.services.live_deployment_gate import _issue_for_demo_auth

    msg = _issue_for_demo_auth(
        where="/api/auth/login",
        status=401,
        body='{"detail":"Invalid credentials"}',
    )
    assert "live_demo_auth_mismatch" in msg
    assert "SANDBOX_DEMO" in msg
    assert "dependency" not in msg.lower() or "missing Python dependency" in msg


def test_mesh_unreachable_reason_is_flagged():
    from web.backend.services.live_deployment_gate import _MESH_UNREACHABLE_RE, _issue_for_mesh_unreachable

    reason = "Mesh unavailable: All connection attempts failed"
    assert _MESH_UNREACHABLE_RE.search(reason)
    msg = _issue_for_mesh_unreachable(where="/api/advisory", status=200, reason=reason)
    assert "live_mesh_unreachable" in msg
    assert "ATLAS_BASE_URL" in msg
    assert not _MESH_UNREACHABLE_RE.search("All hazards unknown")
    assert not _MESH_UNREACHABLE_RE.search("no LIVE readings with values in bbox")



def test_live_gate_dev_fixing_task_carries_scope_and_blocking():
    from web.backend.services.live_deployment_gate import (
        live_gate_dev_fixing_task,
        mark_product_live_gate_failed,
    )

    live_gate = {
        "passed": False,
        "skipped": False,
        "issues": [
            "live_exception_in_ui:/api/advisory:200: unexpected keyword argument 'west'"
        ],
        "repair_scope": ["backend/app/routers/advisory.py", "backend/app/services/atlas_client.py"],
    }
    product = {"id": "prod-x", "idea": "Sentinel", "state": "COMPLETED"}
    mark_product_live_gate_failed(product, live_gate)
    assert product["state"] == "BUG_FOUND"
    task = live_gate_dev_fixing_task("prod-x", product, live_gate)
    assert task["agent_type"] == "developer"
    assert task["state"] == "DEV_FIXING"
    qg = task["input_data"]["quality_gates_feedback"]
    assert qg["passed"] is False
    assert "advisory.py" in " ".join(qg["repair_scope"])
    assert task["input_data"]["live_gate_blocked"] is True


def test_live_api_sweep_fails_on_typeerror_in_advisory(monkeypatch):
    """The HTTP half of the gate, no browser required — this is what Sentinel actually returned."""
    import json

    body = json.dumps(
        {
            "overall": {
                "level": "UNKNOWN",
                "reason": (
                    "ATLAS sensor mesh unavailable: AtlasClient.get_situation_brief() "
                    "got an unexpected keyword argument 'west'"
                ),
            }
        }
    )

    def fake_openapi(_base):
        return {"paths": {}}

    def fake_call(method, url, **_kwargs):
        if "advisory" in url:
            return 200, body
        return 404, ""

    monkeypatch.setattr("web.backend.services.product_demo_journey._openapi", fake_openapi)
    monkeypatch.setattr("web.backend.services.product_demo_journey._call", fake_call)
    issues, report = _sweep_live_api("https://prod-bdb1634806de.vercel.app")
    assert issues, report
    assert any("live_exception_in_ui" in i for i in issues)
    assert any("unexpected keyword" in i for i in issues)
