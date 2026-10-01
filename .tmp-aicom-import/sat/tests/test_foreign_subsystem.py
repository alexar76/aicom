"""Eight of nine blocking defects were in a product the customer never ordered.

The live product is a weather-and-wildfire safety companion. Inside it:

    routers/analytics.py          258 lines, imports 8 names that exist nowhere
    schemas/analytics.py           78 lines
    services/analytics_engine.py    3 lines  — a stub, which is why those 8 never resolve
    models/analytics.py           139 lines, 7 tables: dashboards, charts, datasets, share_links…

478 lines of BI dashboard, registered in `main.py`, in a product whose charter says "autonomous,
LLM-free safety companion … weather, wildfire and flooding … signed evidence receipt … invoking the
ATLAS sensor-mesh". It came from a methodology gate that classified the product as `analytics_bi` and
demanded `POST /api/dashboards` and friends.

So every "define get_dashboard_data" instruction was work in the wrong direction: succeeding at it
would have been worse than failing. One finding that says "this subsystem is not part of this product"
replaces eight that say "write the missing half of it".

Deleting code is the most destructive advice a gate can give, so most of what follows is about the
conditions under which it stays quiet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.foreign_subsystem import MIN_DEFECTS, find_unchartered_subsystems

CHARTER = (
    "Sentinel is an autonomous, LLM-free safety companion that any website can embed. It tells the "
    "visitor, for their own location, what is happening right now with weather, wildfire and "
    "flooding — and it proves every statement with a signed evidence receipt instead of a generated "
    "opinion. Sentinel has no model of its own: it reasons by invoking the ATLAS sensor-mesh "
    "capabilities of the AI factory over the AI-market protocol, and refuses to answer when the "
    "sensors are silent."
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def live_case(tmp_path: Path) -> Path:
    """Reduced from the real tree: a BI cluster whose engine is a stub."""
    return _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": (
                "from app.routers import advisory, analytics\n"
                'app.include_router(analytics.router, prefix="/api/analytics")\n'
            ),
            "backend/app/routers/analytics.py": (
                "from ..schemas.analytics import ChartCreate, FilterCreate, ShareOut\n"
                "from ..services.analytics_engine import get_dashboard_data, export_dashboard_data_csv\n"
            ),
            "backend/app/schemas/analytics.py": "class DashboardCreate:\n    pass\n",
            "backend/app/services/analytics_engine.py": "# TODO\n",
            "backend/app/models/analytics.py": 'class Dashboard:\n    __tablename__ = "dashboards"\n',
            "backend/app/routers/advisory.py": "from ..services.atlas_client import AtlasClient\n",
            "backend/app/services/atlas_client.py": "class AtlasClient:\n    pass\n",
        },
    )


def test_the_live_cluster_is_reported_once_with_all_of_its_files(live_case):
    findings = find_unchartered_subsystems(live_case, CHARTER)
    assert len(findings) == 1, [f["cluster"] for f in findings]
    finding = findings[0]
    assert finding["cluster"] == "analytics"
    assert finding["defect_count"] >= 5
    assert set(finding["files"]) == {
        "backend/app/models/analytics.py",
        "backend/app/routers/analytics.py",
        "backend/app/schemas/analytics.py",
        "backend/app/services/analytics_engine.py",
    }


def test_it_names_where_the_subsystem_is_wired_in(live_case):
    """Deleting a router without unregistering it only changes which ImportError you get."""
    finding = find_unchartered_subsystems(live_case, CHARTER)[0]
    assert "backend/app/main.py" in finding["registered_in"]
    assert "unregister" in finding["detail"]


def test_it_says_not_to_implement_the_missing_names(live_case):
    """The instruction that had been given eight times, and was the wrong direction."""
    detail = find_unchartered_subsystems(live_case, CHARTER)[0]["detail"]
    assert "Do not implement the missing names" in detail
    assert "second product" in detail


def test_chartered_work_is_never_reported(live_case):
    """A charter that does ask for analytics makes those defects ordinary work."""
    charter = CHARTER + " It also ships an analytics dashboard with charts and CSV export."
    assert find_unchartered_subsystems(live_case, charter) == []


def test_a_single_broken_import_is_not_a_subsystem(tmp_path):
    """Below the threshold this is a defect to fix, not evidence of a foreign product."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/telemetry.py": "from ..services.telemetry_engine import ship_metrics\n",
            "backend/app/services/telemetry_engine.py": "# TODO\n",
        },
    )
    assert find_unchartered_subsystems(code, CHARTER) == []
    assert MIN_DEFECTS >= 3


def test_an_empty_charter_produces_no_opinion(live_case):
    """"Nothing is chartered" must never mean "delete everything"."""
    assert find_unchartered_subsystems(live_case, "") == []
    assert find_unchartered_subsystems(live_case, "safety agent") == []


def test_the_products_own_broken_code_is_not_called_foreign(tmp_path):
    """The advisory half is what the charter asks for; broken or not, it stays."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/advisory.py": (
                "from ..services.advisory_engine import compute, verify, receipt, evidence\n"
            ),
            "backend/app/services/advisory_engine.py": "# TODO\n",
        },
    )
    assert find_unchartered_subsystems(code, CHARTER) == []


def test_infrastructure_words_do_not_become_evidence(tmp_path):
    """A charter does not mention a logger, and its absence proves nothing."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/routers/logger.py": (
                "from ..utils.logger import get_logger, set_level, add_handler, flush_logs\n"
            ),
            "backend/app/utils/logger.py": "# TODO\n",
        },
    )
    assert find_unchartered_subsystems(code, CHARTER) == []


def test_the_qa_gate_reports_it_and_ranks_it_first():
    """A subsystem nothing asked for outranks every defect inside it."""
    root = Path(__file__).resolve().parents[1]
    qa = (root / "agents" / "qa.py").read_text(encoding="utf-8")
    assert "find_unchartered_subsystems" in qa, "the gate never runs it"
    head = qa[: qa.index("# Deletions next")]
    assert '"unchartered_subsystem"' in head
    assert head.index('"unchartered_subsystem"') < head.index('"missing_module"'), (
        "a foreign subsystem is ranked below the defects it contains"
    )


def test_it_is_not_double_counted_in_the_developers_score():
    """Its defects are already counted individually as missing symbols; adding the cluster on top
    would make deleting four files look like a bigger win than it is, and the ratchet must not be
    persuadable by arithmetic."""
    dev = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    score = dev[dev.index("def _tree_defect_score(") : dev.index("def _revert_out_of_scope_writes")]
    assert "unchartered" not in score and "foreign_subsystem" not in score


def test_the_gate_reads_the_charter_from_the_store_not_the_task_payload():
    """The detector was correct and silent, which looked exactly like a clean product.

    This product's spec is `{}` and the idea does not always travel with the QA task, so the charter
    QA assembled came to a few dozen characters — below the threshold at which absence proves
    anything — and the gate declined to have an opinion. That is the right behaviour for a short
    charter and the wrong answer here, because the 779-character charter exists; it just lives in the
    product record rather than in the task payload.
    """
    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    # Bound call, not merely the name. The first version wrote `_charter_from_store(...)` without
    # `self.`, so every QA run raised NameError inside the try that guards this gate, swallowed it,
    # and reported no foreign subsystem — the gate looked as if it had run and found nothing. A test
    # asserting only that the name appears somewhere passed happily through that.
    assert "self._charter_from_store(product_id, _charter_text)" in qa
    assert "if len(_charter_text.strip()) < 200:" in qa, (
        "the fallback is unconditional, so the payload can no longer be preferred when it is good"
    )
    loader = qa[qa.index("def _charter_from_store") :][:1400]
    assert "mode=ro" in loader, "the gate opens the pipeline store for writing"
    assert "select idea, spec, extras from products" in loader
    assert "return fallback" in loader, "a store read that fails must not lose the payload charter"


# --- the charter is the order, not what we have said about it -----------------------------------


def test_our_own_findings_never_become_the_charter():
    """The loop this closes, in one line of log:

        Unchartered-subsystem check: charter 28067 chars, 0 finding(s)
          — sample of what the charter covers: … "analytics/bi, …

    The 28k came from dumping the specification payload, which had accumulated the text of a finding:
    `Methodology gate (analytics_bi): domain_api_endpoint_missing`. So a gate complaining that BI
    endpoints were missing became the evidence that BI had been ordered, which protected the BI
    subsystem from removal, which kept the gate complaining. A misclassification licensing itself, and
    my detector was right all three times it stayed quiet — the question it was asked was wrong.
    """
    from core.foreign_subsystem import CHARTER_SPEC_FIELDS, charter_text

    spec = {
        "product_name": "Sentinel",
        "summary": "weather, wildfire and flood safety companion",
        "domain": "analytics_bi",
        "qa_findings": [
            {"title": "Methodology gate (analytics_bi): domain_api_endpoint_missing",
             "description": "API endpoints not covered: POST /api/dashboards"},
        ],
    }
    text = charter_text("an embeddable safety companion", spec, "")
    assert "analytics" not in text.lower(), text
    assert "dashboard" not in text.lower(), text
    assert "wildfire" in text.lower()
    # `domain` is a conclusion of ours, not a line of the order.
    assert "domain" not in CHARTER_SPEC_FIELDS


def test_the_ordered_fields_are_all_carried():
    from core.foreign_subsystem import charter_text

    spec = {
        "specification": {
            "user_stories": [{"story": "as a visitor I see flood risk"}],
            "functional_requirements": [{"title": "signed evidence receipt"}],
            "acceptance_criteria": "refuses to answer when sensors are silent",
        }
    }
    text = charter_text("", spec, "operator dashboard is out of scope")
    for expected in ("flood", "evidence receipt", "sensors are silent", "out of scope"):
        assert expected in text, expected


def test_a_chartered_analytics_product_is_still_protected():
    """The protection must survive: if the order does ask for analytics, the code stays."""
    from core.foreign_subsystem import charter_text

    spec = {"summary": "a BI tool with dashboards, charts and CSV export"}
    text = charter_text("analytics for teams", spec, "")
    assert "analytics" in text.lower() and "dashboard" in text.lower()


def test_qa_assembles_the_charter_through_the_whitelist():
    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    assert "from core.foreign_subsystem import charter_text, find_unchartered_subsystems" in qa
    assert "_charter_text = charter_text(" in qa
    assert 'json.dumps(agent_input.data.get("specification")' not in qa, (
        "the payload is still being dumped wholesale into the charter"
    )
