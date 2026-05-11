from __future__ import annotations

from web.backend.services.domain_methodology import (
    get_domain_pack,
    list_domain_packs,
    score_domain_packs,
    select_domain_pack,
)
from web.backend.services.methodology_review import review_implementation, review_spec
from web.backend.services.marketplace_quality import evaluate_marketplace_quality
from web.backend.services.methodology_knowledge import (
    MethodologyKnowledgeStore,
    MethodologyLesson,
)


def _helpdesk_spec() -> dict:
    return {
        "product_name": "SLA Desk",
        "description": "Helpdesk support ticket platform for service teams",
        "category": "helpdesk",
        "personas": [
            {"name": "Requester", "goals": ["create ticket", "reply to agent"]},
            {"name": "Agent", "goals": ["assign ticket", "resolve incidents"]},
            {"name": "Manager", "goals": ["track SLA breach rate"]},
        ],
        "core_features": [
            {"name": "Ticket queues", "description": "create ticket, assign ticket, change priority, escalate"},
            {"name": "Conversation thread", "description": "thread comments and close and reopen tickets"},
            {"name": "SLA dashboard", "description": "track sla breach and first response time"},
        ],
        "functional_requirements": [
            {"title": "Ticket lifecycle", "description": "new triaged assigned in progress waiting on customer resolved closed"},
        ],
    }


def test_domain_registry_selects_helpdesk_pack() -> None:
    packs = list_domain_packs()
    assert len(packs) >= 10
    assert get_domain_pack("helpdesk_support") is not None

    selected = select_domain_pack("IT helpdesk with SLA tickets", category="support", spec=_helpdesk_spec())
    assert selected is not None
    assert selected.domain_id == "helpdesk_support"


def test_review_spec_blocks_domain_shape_gaps() -> None:
    pack = get_domain_pack("helpdesk_support")
    weak_spec = {
        "product_name": "Support Site",
        "description": "A nice landing page for support services",
        "core_features": [{"name": "Hero", "description": "marketing copy and a contact button"}],
    }

    report = review_spec(weak_spec, pack=pack)
    assert report["passed"] is False
    assert "domain_methodology_below_threshold" in {f["code"] for f in report["findings"]}


def test_review_spec_passes_when_domain_process_is_explicit() -> None:
    pack = get_domain_pack("helpdesk_support")
    report = review_spec(_helpdesk_spec(), pack=pack)
    assert report["passed"] is True
    assert report["score"] >= 60


def test_review_implementation_blocks_missing_process(tmp_path) -> None:
    pid_dir = tmp_path / "code" / "prod-1"
    pid_dir.mkdir(parents=True)
    (pid_dir / "index.html").write_text(
        "<main><h1>Support Portal</h1><p>Beautiful helpdesk marketing page.</p></main>",
        encoding="utf-8",
    )

    report = review_implementation(pid_dir, pack=get_domain_pack("helpdesk_support"), spec=_helpdesk_spec())
    assert report["passed"] is False
    assert any(f["severity"] == "high" for f in report["findings"])


def test_marketplace_rejects_methodology_failures(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_QUALITY_GATE", "1")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_MIN_SPEC_COVERAGE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_DESIGN_NOVELTY", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_QA_REALISM", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_RELEASE_SCORE", "0")
    monkeypatch.setenv("AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY", "1")

    pid = "prod-methodology-fail"
    code = tmp_path / "code" / pid
    code.mkdir(parents=True)
    (code / "index.html").write_text(
        """<!doctype html><html lang="en"><head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="stylesheet" href="./style.css" />
        <title>SLA Desk</title></head><body><main>
        <h1>SLA Desk</h1>
        <p>Support operations workspace for service teams with compelling benefits and dashboards.</p>
        <section><h2>Overview</h2><p>Operational reporting, collaboration, and inbox visibility.</p></section>
        <section><h2>Workspace</h2><p>Shared views, filters, responsible teams, and performance summaries.</p></section>
        <section><h2>Reliability</h2><p role="status" aria-live="polite">System ready.</p><p role="alert">Validation feedback appears here.</p></section>
        <section aria-busy="true"><h2>Loading</h2><p class="skeleton">Loading workspace data...</p></section>
        <section><h2>Empty state</h2><p>No records yet. Create your first workflow.</p></section>
        <button type="button">Start</button>
        </main></body></html>""",
        encoding="utf-8",
    )
    (code / "style.css").write_text(
        """:root{--bg:#020617;--fg:#e2e8f0;--accent:#38bdf8;--muted:#94a3b8}
        body{background:var(--bg);color:var(--fg);font-family:Inter,system-ui,sans-serif}
        main{max-width:860px;margin:auto;padding:32px}
        section{border:1px solid var(--accent);margin:16px 0;padding:16px;border-radius:16px}
        button:focus-visible,a:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
        .skeleton{animation:pulse 1.2s infinite;color:var(--muted)}
        @keyframes pulse{50%{opacity:.45}}
        @media(max-width:720px){main{padding:18px}section{border-radius:12px}}""",
        encoding="utf-8",
    )

    ev = evaluate_marketplace_quality(pid, specification=_helpdesk_spec(), data_root=str(tmp_path))
    assert ev["eligible"] is False
    assert "methodology_review_failed" in ev["reasons"]


# -------------------- v2 schema --------------------------------------------


def test_v2_pack_has_lifecycle_transitions_and_api() -> None:
    pack = get_domain_pack("helpdesk_support")
    assert pack is not None
    assert pack.lifecycle_states, "lifecycle states present"
    assert pack.lifecycle_transitions, "lifecycle graph present"
    assert pack.api_endpoints, "API endpoints declared"
    assert pack.acceptance_scenarios, "acceptance scenarios declared"
    assert pack.process_metrics_definitions, "KPIs declared with formula"
    assert any(rf.severity == "high" for rf in pack.red_flags)
    payload = pack.to_payload(full=True)
    assert payload["schema_version"] == 2
    assert "lifecycle_transitions" in payload
    assert "api_endpoints" in payload


def test_score_domain_packs_ranks_correctly() -> None:
    ranking = score_domain_packs(
        "online store with checkout, cart, refunds and inventory",
        category="ecommerce",
    )
    assert ranking, "ranking not empty"
    top, score = ranking[0]
    assert top.domain_id == "ecommerce"
    assert score >= 6


def test_review_implementation_detects_api_gap(tmp_path) -> None:
    pack = get_domain_pack("helpdesk_support")
    code_dir = tmp_path / "code" / "p2"
    code_dir.mkdir(parents=True)
    (code_dir / "main.py").write_text(
        """from fastapi import FastAPI
app = FastAPI()
@app.get('/api/tickets')
def list_tickets(): return []
""",
        encoding="utf-8",
    )
    report = review_implementation(code_dir, pack=pack, spec=_helpdesk_spec())
    api = report["checks"]["api"]
    assert any("POST /api/tickets" in m for m in api["missing"])
    assert any("GET /api/tickets" in p for p in api["present"])


def test_lessons_inject_extra_red_flag(tmp_path) -> None:
    pack = get_domain_pack("helpdesk_support")
    store = MethodologyKnowledgeStore(data_root=str(tmp_path))
    store.add_lesson(
        MethodologyLesson(
            id="",
            domain="helpdesk_support",
            severity="high",
            title="No SLA timer",
            detail="Tickets without SLA timer escape ownership",
            keywords=["no sla timer"],
            applies_to=["spec"],
        )
    )
    spec = {
        "product_name": "Helpdesk no SLA",
        "description": (
            "We track tickets new triaged assigned in progress resolved closed "
            "with assignment thread comments search and filter SLA policy is missing — "
            "no sla timer is enforced."
        ),
        "core_features": [
            {"name": "Tickets", "description": "create ticket assign ticket reply"},
            {"name": "Queues", "description": "team queue with priority"},
        ],
    }
    report = review_spec(spec, pack=pack, knowledge=store)
    codes = [f["code"] for f in report["findings"]]
    assert "methodology_learned_red_flag" in codes


def test_review_persists_case_history(tmp_path) -> None:
    pack = get_domain_pack("helpdesk_support")
    store = MethodologyKnowledgeStore(data_root=str(tmp_path))
    weak = {"product_name": "Static page", "description": "marketing only"}
    report = review_spec(
        weak, pack=pack, knowledge=store, persist_case=True, product_id="prod-7",
    )
    assert "case_id" in report
    history = store.get_case_history("prod-7")
    assert len(history) == 1 and history[0].passed is False
