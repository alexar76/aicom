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

import json
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
    assert "live_gate_dev_fixing_task" in EXECUTOR
    assert "live_gate_blocked" in GATE
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
    # Soft placeholder must fail the gate — Sentinel shipped with this as "passed".
    assert _MESH_UNREACHABLE_RE.search("mesh response unavailable")
    assert _MESH_UNREACHABLE_RE.search('{"overall":{"reason":"mesh response unavailable"}}')


def test_insufficient_balance_is_payment_ops_not_a_code_defect():
    """Sentinel live advisory reached Hub and still sat UNKNOWN — the channel was empty.

    Developer rewriting atlas_client.py cannot mint USDC. The gate must fail (not ship
    UNKNOWN as green) and the repair path must park, not enqueue DEV_FIXING.
    """
    from web.backend.services.live_deployment_gate import (
        _MESH_PAYMENT_RE,
        _issue_for_mesh_payment,
        live_gate_is_payment_ops,
        park_product_live_mesh_payment_ops,
    )

    assert _MESH_PAYMENT_RE.search("insufficient balance")
    assert _MESH_PAYMENT_RE.search("payment_authorization_required: escrow channel x is not open on chain")
    msg = _issue_for_mesh_payment(
        where="/api/advisory",
        status=200,
        reason="insufficient balance",
    )
    assert "live_mesh_payment_ops" in msg
    assert "reopen_product_escrow_channel" in msg
    live_gate = {"passed": False, "skipped": False, "issues": [msg]}
    assert live_gate_is_payment_ops(live_gate) is True
    product = {"id": "prod-bdb1634806de", "state": "QA_TESTING"}
    park_product_live_mesh_payment_ops(product, live_gate)
    assert product["state"] == "HUMAN_REVIEW_PENDING"
    assert product["human_review_kind"] == "live_mesh_payment_ops"
    assert product.get("operator_locked") is True


def test_executor_parks_payment_ops_instead_of_developer():
    assert "live_mesh_payment_parked" in EXECUTOR
    assert "no developer, repair budget not charged" in EXECUTOR
    assert "live_gate_dev_fixing_task" in EXECUTOR


def test_executor_heals_demo_auth_itself_instead_of_waiting_for_cursor():
    """The factory must patch+republish the known login-401 class. Cursor SSH is not the loop."""
    assert "try_factory_live_auth_heal" in EXECUTOR
    assert "Live auth autofix healed" in EXECUTOR
    assert "relay_source_uuid_pk_mismatch" in EXECUTOR
    assert "relay_source_pinned_mismatch" in EXECUTOR
    assert "apply_live_auth_autofix" in (
        ROOT / "web" / "backend" / "services" / "vercel_fullstack_adapter.py"
    ).read_text(encoding="utf-8")


def test_live_gate_is_demo_auth_and_not_a_typeerror():
    from web.backend.services.live_deployment_gate import live_gate_is_demo_auth

    assert live_gate_is_demo_auth(
        {"issues": ["live_demo_auth_mismatch:POST /api/auth/login:401 Invalid credentials"]}
    )
    assert live_gate_is_demo_auth(
        {"issues": ["live_session_not_durable:/api/operator/spend:401 Invalid token"]}
    )
    assert not live_gate_is_demo_auth(
        {"issues": ["live_exception_in_ui:/api/advisory:200: unexpected keyword argument 'west'"]}
    )


def test_try_factory_live_auth_heal_patches_and_republishes(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-auth-heal"
    routers = tmp_path / "code" / pid / "backend" / "app" / "routers"
    routers.mkdir(parents=True)
    (routers / "auth.py").write_text(
        "from ..db import get_db\n"
        "_demo_seeded = False\n"
        "async def login(login_data, db):\n"
        "    global _demo_seeded\n"
        "    if not _demo_seeded:\n"
        "        x = 1\n"
        "        _demo_seeded = True\n"
        '    token = jwt.encode({"sub": str(user.id)}, secret)\n',
        encoding="utf-8",
    )
    product = {"id": pid, "state": "DEPLOYING"}
    live_gate = {
        "passed": False,
        "skipped": False,
        "issues": ["live_demo_auth_mismatch:POST /api/auth/login:401 Invalid credentials"],
    }

    def fake_publish(_pid):
        return {"ok": True, "live_gate": {"passed": True, "skipped": False, "issues": []}}

    monkeypatch.setattr(
        "web.backend.services.auto_publish.try_publish_after_devops",
        fake_publish,
    )
    from web.backend.services.live_deployment_gate import try_factory_live_auth_heal

    out = try_factory_live_auth_heal(pid, product, live_gate, data_root=str(tmp_path))
    assert out["healed"] is True
    assert out["applied"]
    auth = (routers / "auth.py").read_text(encoding="utf-8")
    assert "seed_demo_user(db)" in auth
    assert product.get("live_auth_autofix_republished") is True
    # Second pass must not publish again.
    out2 = try_factory_live_auth_heal(pid, product, live_gate, data_root=str(tmp_path))
    assert out2["healed"] is False and out2["applied"] == []


def test_try_factory_live_auth_heal_skips_non_auth_defects(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-typeerror"
    (tmp_path / "code" / pid).mkdir(parents=True)
    called = []
    monkeypatch.setattr(
        "web.backend.services.auto_publish.try_publish_after_devops",
        lambda _pid: called.append(_pid) or {"ok": True},
    )
    from web.backend.services.live_deployment_gate import try_factory_live_auth_heal

    out = try_factory_live_auth_heal(
        pid,
        {"id": pid},
        {
            "passed": False,
            "issues": ["live_exception_in_ui:/api/advisory: unexpected keyword argument 'west'"],
        },
        data_root=str(tmp_path),
    )
    assert out == {"healed": False, "applied": []}
    assert called == []


def test_try_factory_live_auth_heal_on_relay_salt_mismatch_without_demo_auth(tmp_path, monkeypatch):
    """Vercel-green login must not hide a source salt mismatch — factory still heals data/code."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-relay-salt"
    app = tmp_path / "code" / pid / "backend" / "app"
    routers = app / "routers"
    routers.mkdir(parents=True)
    (app / "security.py").write_text(
        'serializer = URLSafeTimedSerializer("s", salt="relay-session")\n'
        "def create_session_token(oid: str) -> str:\n    return oid\n",
        encoding="utf-8",
    )
    (routers / "auth.py").write_text(
        "def _create_access_token(operator_id) -> str:\n"
        "    from itsdangerous import URLSafeTimedSerializer\n"
        '    serializer = URLSafeTimedSerializer("dev-secret")\n'
        '    return serializer.dumps({"sub": str(operator_id)}, salt="relay-access-token")\n'
        "@router.post('/api/auth/login')\n"
        "def login_api():\n    return {}\n",
        encoding="utf-8",
    )
    (routers / "handoffs.py").write_text(
        's = URLSafeTimedSerializer(secret, salt="relay-session")\n',
        encoding="utf-8",
    )
    published = []

    def fake_publish(_pid):
        published.append(_pid)
        return {"ok": True, "live_gate": {"passed": True, "skipped": False, "issues": []}}

    monkeypatch.setattr(
        "web.backend.services.auto_publish.try_publish_after_devops",
        fake_publish,
    )
    from web.backend.services.live_deployment_gate import try_factory_live_auth_heal

    product = {"id": pid, "state": "QA_TESTING"}
    out = try_factory_live_auth_heal(
        pid,
        product,
        {"passed": True, "skipped": False, "issues": []},
        data_root=str(tmp_path),
    )
    assert out["healed"] is True
    assert any("relay_token_salt" in a for a in out["applied"])
    auth = (routers / "auth.py").read_text(encoding="utf-8")
    assert "relay-access-token" not in auth
    assert published == [pid]


def test_try_factory_live_auth_heal_on_relay_uuid_pk_after_salt_republished(tmp_path, monkeypatch):
    """Login 200 must not hide Operator.id == operator_id → UUID column 500."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-relay-uuid"
    app = tmp_path / "code" / pid / "backend" / "app"
    routers = app / "routers"
    routers.mkdir(parents=True)
    (routers / "handoffs.py").write_text(
        "def verify_access_token(token, db):\n"
        "    operator_id = data.get('sub')\n"
        "    return db.query(Operator).filter(Operator.id == operator_id).first()\n",
        encoding="utf-8",
    )
    published = []

    def fake_publish(_pid):
        published.append(_pid)
        return {"ok": True, "live_gate": {"passed": True, "skipped": False, "issues": []}}

    monkeypatch.setattr(
        "web.backend.services.auto_publish.try_publish_after_devops",
        fake_publish,
    )
    from web.backend.services.live_deployment_gate import try_factory_live_auth_heal

    product = {
        "id": pid,
        "state": "QA_TESTING",
        "live_auth_autofix_republished": True,
    }
    out = try_factory_live_auth_heal(
        pid,
        product,
        {
            "passed": True,
            "skipped": False,
            "issues": ["live_exception_in_ui:/api/handoffs:500 PG UUID type requires Python uuid.UUID"],
        },
        data_root=str(tmp_path),
    )
    assert out["healed"] is True
    assert any("relay_uuid_pk" in a for a in out["applied"])
    handoffs = (routers / "handoffs.py").read_text(encoding="utf-8")
    assert 'UUID(str(operator_id))' in handoffs
    assert "Operator.id == operator_id" not in handoffs
    assert published == [pid]
    out2 = try_factory_live_auth_heal(
        pid,
        product,
        {"passed": True, "skipped": False, "issues": []},
        data_root=str(tmp_path),
    )
    assert out2["healed"] is False and out2["applied"] == []


def test_try_factory_live_auth_heal_on_relay_pinned_enum_after_uuid_republished(tmp_path, monkeypatch):
    """Login 200 / UUID already healed must not hide receipt enum UUID 500s."""
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    pid = "prod-relay-pinned"
    app = tmp_path / "code" / pid / "backend" / "app"
    services = app / "services"
    routers = app / "routers"
    services.mkdir(parents=True)
    routers.mkdir(parents=True)
    (routers / "handoffs.py").write_text("router = APIRouter()\n", encoding="utf-8")
    (services / "receipt.py").write_text(
        'return {"handoff_id": handoff.id, "approval_state": handoff.status.value}\n',
        encoding="utf-8",
    )
    published = []

    def fake_publish(_pid):
        published.append(_pid)
        return {"ok": True, "live_gate": {"passed": True, "skipped": False, "issues": []}}

    monkeypatch.setattr(
        "web.backend.services.auto_publish.try_publish_after_devops",
        fake_publish,
    )
    from web.backend.services.live_deployment_gate import try_factory_live_auth_heal

    product = {"id": pid, "state": "QA_TESTING", "live_auth_autofix_republished": True}
    out = try_factory_live_auth_heal(
        pid,
        product,
        {"passed": True, "skipped": False, "issues": []},
        data_root=str(tmp_path),
    )
    assert out["healed"] is True
    assert any("relay_pinned" in a for a in out["applied"])
    receipt = (services / "receipt.py").read_text(encoding="utf-8")
    assert "str(handoff.id)" in receipt
    assert published == [pid]


def test_live_gate_blocks_completion_on_demo_auth_401_even_if_passed_stamped():
    """operator_complete --force used to COMPLETE over a recorded live 401."""
    from web.backend.services.live_deployment_gate import live_gate_blocks_completion

    product = {
        "live_gate": {
            "passed": True,
            "skipped": False,
            "issues": [
                "live_demo_auth_mismatch:POST /api/auth/login:401 on the DEPLOYED site. "
                "Invalid credentials"
            ],
        }
    }
    reason = live_gate_blocks_completion(product)
    assert reason
    assert "live_demo_auth_mismatch" in reason
    assert live_gate_blocks_completion({"live_gate": {"passed": True, "issues": []}}) is None
    assert live_gate_blocks_completion({"live_gate": {"passed": False, "issues": ["x"]}})
    assert live_gate_blocks_completion({"live_gate": {"skipped": True, "passed": False}}) is None


def test_operator_complete_script_refuses_live_auth_401_even_with_force():
    src = (ROOT / "scripts" / "operator_complete_product.py").read_text(encoding="utf-8")
    assert "live_gate_blocks_completion" in src
    assert "--ignore-live-gate" in src
    assert "Does not skip a failed live gate" in src


def test_developer_fail_fast_invalid_json_is_documented():
    """Invalid JSON must not burn the full 1500s execute budget (3×600s)."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "max_invalid_json = 2" in src
    assert "fail-fast: do not burn the 1500s execute budget" in src
    assert "AIFACTORY_CODE_GEN_FAILOVER_MODEL" in src



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


def test_a_401_is_only_excused_when_that_path_also_succeeded():
    """The hole that shipped Sentinel's operator dashboard.

    Every browser 401 on /api/* used to be discarded because the HTTP sweep's login returned a
    token. That token proved the endpoint answers on the instance the login just warmed — not
    that the visitor's session works. A 401 on a path that never answered 2xx is a finding.
    """
    assert "path in ok_paths" in GATE
    assert "ok_paths: set[str] = set()" in GATE
    guard = GATE[GATE.index("Crawling /#/operator") :]
    assert "login_ok = any(" not in guard[: guard.index("_is_demo_auth_failure")]


def test_console_401_excuse_requires_a_durable_session():
    """A console 401 has no path to correlate, so it may only be excused when the durability
    probe actually proved the session survives."""
    tail = GATE[GATE.index("for ce in console_errors") :]
    assert "session_durability" in tail
    assert "login_ok and durable" in tail


def test_the_gate_probes_session_durability_not_one_warm_instance():
    assert "_probe_session_durability" in GATE
    assert "live_ephemeral_identity" in GATE
    assert "live_session_not_durable" in GATE
    assert "distinct_subjects" in GATE


def test_ephemeral_identity_scope_names_the_model_and_session_dependency(tmp_path):
    code = tmp_path / "code"
    (code / "backend" / "app" / "models").mkdir(parents=True)
    (code / "backend" / "app").joinpath("deps.py").write_text(
        "def get_current_user():\n    ...\n", encoding="utf-8"
    )
    (code / "backend" / "app" / "models" / "user.py").write_text(
        "id = Column(String(36), primary_key=True, default=gen_uuid)\n", encoding="utf-8"
    )
    scope = _repair_scope_from_issues(
        [
            "live_ephemeral_identity:/api/auth/login: 6 logins with the same credentials "
            "minted 6 different user identities on the DEPLOYED site."
        ],
        code,
    )
    assert "backend/app/models/user.py" in scope
    assert "backend/app/deps.py" in scope


def test_distinct_subjects_across_logins_is_a_finding(monkeypatch):
    """Measured on the live deployment: 10 logins, 9 distinct `sub` claims."""
    import base64
    import itertools

    counter = itertools.count()

    def fake_login(_base, _path, _email, _password):
        claims = {"sub": f"uuid-{next(counter)}", "email": "d@e.f"}
        blob = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return f"h.{blob}.s", {}

    monkeypatch.setattr("web.backend.services.product_demo_journey.attempt_login", fake_login)
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._call", lambda *a, **k: (200, "{}")
    )
    from web.backend.services.live_deployment_gate import _probe_session_durability

    issues, report = _probe_session_durability(
        "https://x.vercel.app", "/api/auth/login", "d@e.f", "pw", {"/api/operator/spend": {"get": {}}}
    )
    assert report["distinct_subjects"] > 1
    assert any("live_ephemeral_identity" in i for i in issues)


def test_a_stable_identity_with_working_replays_passes(monkeypatch):
    import base64

    claims = {"sub": "stable-uuid", "email": "d@e.f"}
    blob = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey.attempt_login",
        lambda *a, **k: (f"h.{blob}.s", {}),
    )
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._call", lambda *a, **k: (200, "{}")
    )
    from web.backend.services.live_deployment_gate import _probe_session_durability

    issues, report = _probe_session_durability(
        "https://x.vercel.app", "/api/auth/login", "d@e.f", "pw", {"/api/operator/spend": {"get": {}}}
    )
    assert report["distinct_subjects"] == 1
    assert issues == []


def test_a_rejected_replay_is_a_finding(monkeypatch):
    """Stable identity, but the token stops working — the other half of the same failure."""
    import base64

    claims = {"sub": "stable-uuid", "email": "d@e.f"}
    blob = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey.attempt_login",
        lambda *a, **k: (f"h.{blob}.s", {}),
    )
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._call",
        lambda *a, **k: (401, '{"detail":"User not found"}'),
    )
    from web.backend.services.live_deployment_gate import _probe_session_durability

    issues, _report = _probe_session_durability(
        "https://x.vercel.app", "/api/auth/login", "d@e.f", "pw", {"/api/operator/spend": {"get": {}}}
    )
    assert any("live_session_not_durable" in i for i in issues)


def test_probe_paths_prefer_protected_routes():
    from web.backend.services.live_deployment_gate import _protected_probe_paths

    paths = {
        "/api/health": {"get": {}},
        "/api/operator/spend": {"get": {}},
        "/api/operator/audit": {"get": {}},
        "/api/analytics/dashboards/{dashboard_id}": {"get": {}},
        "/api/auth/login": {"post": {}},
        "/api/workspace/branding": {"get": {}},
    }
    got = _protected_probe_paths(paths)
    assert "/api/operator/spend" in got
    assert "/api/operator/audit" in got
    assert "/api/workspace/branding" in got
    assert "/api/auth/me" in got, "fallback auth features must be probed even if OpenAPI omits them"
    assert not any("{" in p for p in got), "a templated path cannot be probed as-is"
    assert "/api/auth/login" not in got


def test_authed_feature_5xx_is_a_gate_failure(monkeypatch):
    """Relay: login + /me 200, /api/workspace/branding 500 — must fail the live gate."""
    from web.backend.services import live_deployment_gate as gate
    from web.backend.services import product_demo_journey as journey

    monkeypatch.setattr(journey, "attempt_login", lambda *a, **k: ("tok-1", {}))

    def _call(method, url, token=None, timeout=60.0):
        if url.endswith("/api/workspace/branding"):
            return 500, '{"detail":"internal error"}'
        if url.endswith("/api/auth/me"):
            return 200, '{"ok":true}'
        if url.endswith("/api/handoffs"):
            return 200, '{"items":[]}'
        return 404, ""

    monkeypatch.setattr(journey, "_call", _call)
    issues, report = gate._probe_session_durability(
        "https://example.test",
        "/api/auth/login",
        "sandbox.demo@magic-ai-factory.com",
        "pw",
        {"/api/health": {"get": {}}},
    )
    assert any("live_authed_feature_dead:/api/workspace/branding:500" in i for i in issues)
    assert report.get("feature_5xx")
    assert "internal error" in " ".join(issues)


def test_repair_scope_names_branding_auth_files_for_authed_5xx(tmp_path):
    from web.backend.services.live_deployment_gate import _repair_scope_from_issues

    code = tmp_path / "prod"
    (code / "backend/app/routers").mkdir(parents=True)
    (code / "backend/app/schemas").mkdir(parents=True)
    (code / "frontend/src/pages").mkdir(parents=True)
    for rel in (
        "backend/app/deps.py",
        "backend/app/routers/auth.py",
        "backend/app/routers/workspace.py",
        "backend/app/schemas/branding.py",
        "frontend/src/api.ts",
        "frontend/src/pages/Branding.tsx",
    ):
        (code / rel).write_text("# stub\n", encoding="utf-8")
    named = _repair_scope_from_issues(
        [
            "live_authed_feature_dead:/api/workspace/branding:500 on the DEPLOYED site "
            "after a 200 login. Body: {\"detail\":\"internal error\"}."
        ],
        code,
    )
    assert "backend/app/deps.py" in named
    assert "backend/app/routers/workspace.py" in named
    assert "frontend/src/pages/Branding.tsx" in named

def test_a_returned_tuple_is_read_as_the_error_it_meant_to_be():
    """Sentinel's SPA catch-all did `return {"detail": "Not Found"}, 404`.

    FastAPI made the tuple the body and left the status line at 200, so every unknown /api/
    path answered 200 and nothing downstream could tell a missing route from a working one.
    """
    from web.backend.services.live_deployment_gate import _returned_tuple_status

    assert _returned_tuple_status('[{"detail":"Not Found"},404]') == 404
    assert _returned_tuple_status('["gone", 410]') == 410
    assert _returned_tuple_status('[{"detail":"boom"},500,{"x":"y"}]') == 500


def test_the_tuple_check_does_not_fire_on_ordinary_bodies():
    """A gate that un-publishes products cannot afford this one to be loose."""
    from web.backend.services.live_deployment_gate import _returned_tuple_status

    for body in (
        '{"detail":"Not Found"}',            # an honest 404 body, with an honest 404 status
        "[1, 404]",                          # plain numbers
        "[404]",                             # single element
        '[{"a":1},{"b":2}]',                 # a normal collection
        '[{"a":1},200]',                     # success codes are not this defect
        '[{"a":1},99]',                      # not an HTTP status
        '[{"a":1},true]',                    # bool is an int subclass — must not match
        '{"items":[{"detail":"x"},404]}',     # nested, not the response shape
        "not json at all",
        "",
    ):
        assert _returned_tuple_status(body) is None, body


def test_an_undefined_api_route_must_not_answer_2xx(monkeypatch):
    from web.backend.services.live_deployment_gate import (
        _MISSING_API_PROBE,
        _probe_unknown_api_path,
    )

    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._call",
        lambda *a, **k: (200, '[{"detail":"Not Found"},404]'),
    )
    issues, report = _probe_unknown_api_path("https://x.vercel.app")
    assert report["path"] == _MISSING_API_PROBE
    assert any("api_status_contract" in i for i in issues)
    assert any("404" in i for i in issues)


def test_a_catch_all_serving_html_under_api_is_also_a_finding(monkeypatch):
    """Same defect, different body: the SPA index served for an /api/ path."""
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._call",
        lambda *a, **k: (200, "<!doctype html><title>App</title>"),
    )
    from web.backend.services.live_deployment_gate import _probe_unknown_api_path

    issues, _report = _probe_unknown_api_path("https://x.vercel.app")
    assert any("api_missing_route_is_200" in i for i in issues)


def test_a_proper_404_on_an_undefined_route_passes(monkeypatch):
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._call",
        lambda *a, **k: (404, '{"detail":"Not Found"}'),
    )
    from web.backend.services.live_deployment_gate import _probe_unknown_api_path

    issues, report = _probe_unknown_api_path("https://x.vercel.app")
    assert issues == []
    assert report["status"] == 404


def test_the_status_contract_finding_names_the_entrypoint():
    """A repair round has to open the catch-all, not the router that looks related."""
    from web.backend.services.live_deployment_gate import _issue_for_returned_tuple

    msg = _issue_for_returned_tuple(
        where="/api/operator/dashboard", status=200, code=404, body='[{"detail":"Not Found"},404]'
    )
    scope = _repair_scope_from_issues([msg], None)
    assert "backend/app/main.py" in scope
    assert "JSONResponse" in msg and "HTTPException" in msg


def test_the_sweep_probes_for_a_missing_route(monkeypatch):
    """The probe has to run even when OpenAPI is empty — that is the case where a catch-all
    is most likely to be swallowing everything."""
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._openapi", lambda _b: {"paths": {}}
    )
    monkeypatch.setattr(
        "web.backend.services.product_demo_journey._call",
        lambda _m, url, **_k: (200, '[{"detail":"Not Found"},404]'),
    )
    issues, report = _sweep_live_api("https://x.vercel.app")
    assert report["missing_route_probe"]["status"] == 200
    assert any("api_status_contract" in i for i in issues)


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
