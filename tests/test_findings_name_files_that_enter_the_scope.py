"""A finding that names a line and a scope that forbids editing it cannot both be right.

Measured on a product down to four defects. `missing_attribute` is filed against the CLASS —
atlas_client.py, heartbeat.py — while the fix belongs where the attribute is READ:

    HeartbeatService never declares 'scheduler', read as heartbeat.scheduler at main.py:47
    AtlasClient never declares 'get_advisory', read as atlas.get_advisory at advisory.py:35

The repair scope held only the two class files. A round editing either read site — the only place
where `heartbeat.stop()` and a real client method can go — would have had that work reverted as
out-of-scope sprawl. Round 19 wrote twelve edits across seven other files and the three findings
survived untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = (ROOT / "agents" / "qa.py").read_text(encoding="utf-8")


def test_the_scope_collects_paths_named_in_finding_details():
    block = QA[QA.index("_named_paths = re.findall(") :][:900]
    assert "detail" in block, "the paths live in the detail text"
    assert "blocking_files.append(_clean)" in block


def test_only_serious_findings_contribute_paths():
    block = QA[QA.index("_named_paths = re.findall(") :][:900]
    assert '("critical", "high")' in block, "a low-severity note must not widen the scope"


def test_the_product_prefix_is_stripped():
    """Gate issues arrive as either repo-relative or code/<pid>/<path>."""
    block = QA[QA.index("_named_paths = re.findall(") :][:900]
    assert '_np.split(f"{product_id}/", 1)[-1]' in block


def test_the_pattern_matches_a_path_with_a_line_number():
    pattern = re.compile(r"\b((?:[\w.-]+/)+[\w.-]+\.(?:py|ts|tsx|js|jsx))(?::\d+)?")
    text = (
        "HeartbeatService never declares 'scheduler', read as heartbeat.scheduler at "
        "backend/app/main.py:47. Python raises AttributeError"
    )
    assert pattern.findall(text) == ["backend/app/main.py"]


def test_the_pattern_ignores_prose_and_bare_module_names():
    """`app.main` and `AtlasClient` are not paths, and a scope full of non-files is no scope."""
    pattern = re.compile(r"\b((?:[\w.-]+/)+[\w.-]+\.(?:py|ts|tsx|js|jsx))(?::\d+)?")
    assert pattern.findall("AtlasClient never declares get_advisory in app.main") == []


def test_it_runs_before_the_scope_is_truncated():
    """The scope keeps the first six by rank; paths added after that are silently dropped."""
    added = QA.index("_named_paths = re.findall(")
    truncated = QA.index("Repair scope truncated to the first 6")
    assert added < truncated


def test_compile_and_auth_files_are_seeded_before_module_health():
    """Otherwise unstyled operator TSX fills the six slots and PublicWidget.tsx never enters."""
    qa = QA
    seed = qa.index("Compile + auth-rejected first")
    module_health = qa.index("for _gate in (module_health, api_contract):")
    truncated = qa.index("Repair scope truncated to the first 6")
    assert seed < module_health < truncated


def test_boot_fatal_files_lead_the_truncated_six():
    """Otherwise tsc unused-React fills the six and atlas_client.py never enters."""
    qa = QA
    assert "_BOOT_FATAL_SCOPE_CODES" in qa
    assert "mesh_contract_violation" in qa[qa.index("_BOOT_FATAL_SCOPE_CODES") :][:500]
    assert "unexpected_keyword_argument" in qa[qa.index("_BOOT_FATAL_SCOPE_CODES") :][:500]
    assert "missing_symbol" in qa[qa.index("_BOOT_FATAL_SCOPE_CODES") :][:500]
    lead = qa[qa.index("_lead_needles: list[str] = []") : qa.index("repair_scope = blocking_files[:6]")]
    boot = lead.index("_boot_fatal_scope_files")
    compile_files = lead.index("for _line in frontend_build.get")
    assert boot < compile_files, "mesh/boot-fatal files must occupy slot 1 before tsc TSX"


def test_boot_fatal_helper_keeps_atlas_and_drops_unstyled_tsx():
    from core.repair_batches import _files_in

    start = QA.index("_BOOT_FATAL_SCOPE_CODES")
    end = QA.index("\ndef _landing_skip_methodology_gate")
    ns = {
        "_files_in": _files_in,
        "_SCOPE_FILE_SUFFIXES": (".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css"),
    }
    exec("from __future__ import annotations\n" + QA[start:end], ns)
    mh = {
        "issues": [
            {
                "code": "mesh_contract_violation",
                "file": "backend/app/services/atlas_client.py",
                "detail": "invoke envelope extra keys at backend/app/services/atlas_client.py",
            },
            {
                "code": "unstyled_classes",
                "file": "frontend/src/pages/SpendSummary.tsx",
                "detail": "text-muted",
            },
        ]
    }
    assert ns["_boot_fatal_scope_files"](mh, "prod-x") == [
        "backend/app/services/atlas_client.py"
    ]


def test_landing_markup_is_seeded_when_visual_gates_fail():
    """Otherwise operator TSX fills the six slots and index.html is reverted as sprawl."""
    qa = QA
    seed = qa.index("Landing markup. Demo/TZ")
    trunc = qa.index("Repair scope truncated to the first 6")
    assert "_LANDING_SCOPE_CANDIDATES" in qa
    assert '".html"' in qa[qa.index("_SCOPE_FILE_SUFFIXES") : qa.index("_SCOPE_FILE_SUFFIXES") + 200]
    assert seed < trunc
    assert "index.html" in qa[seed : seed + 900]
    assert "frontend/src/pages/PublicWidget.tsx" in qa


def test_spa_consoles_lead_only_when_the_browser_is_red():
    """Operator dashboards in the six when E2E is already green hid the CSS contrast fix.

    After Sentinel's preview stopped throwing, the leftover was ux_low_contrast_cta and the
    truncated six was still App + three dashboards + index.html. The round edited operator
    pages instead of styles. SPA consoles stay first only while the browser is red.
    """
    qa = QA
    assert "_SPA_SCOPE_CANDIDATES" in qa
    lead = qa[qa.index("_lead_needles: list[str] = []") : qa.index("repair_scope = blocking_files[:6]")]
    assert "if not _api_crash and not browser_ok:" in lead
    assert "elif not _api_crash and not demo_gates_ok:" in lead
    spa = lead.index("_SPA_SCOPE_CANDIDATES")
    landing = lead.index("_LANDING_SCOPE_CANDIDATES")
    assert spa < landing
    assert "frontend/src/pages/OperatorDashboard.tsx" in qa[qa.index("_SPA_SCOPE_CANDIDATES") :][:800]

def test_api_crash_keeps_landing_out_of_the_lead():
    """Demo is red because of the 500; landing-in-lead then hid advisory.py."""
    qa = QA
    assert "_journey_has_api_crash" in qa
    assert "demo_journey_5xx" in qa[qa.index("_API_CRASH_MARKERS") :][:400]
    lead = qa[qa.index("_lead_needles: list[str] = []") : qa.index("repair_scope = blocking_files[:6]")]
    assert "not _api_crash" in lead
    crash = lead.index("_journey_line_is_api_crash")
    landing = lead.index("_LANDING_SCOPE_CANDIDATES")
    assert crash < landing
    assert "_RATE_LIMIT_SCOPE_CANDIDATES" in lead


def test_api_crash_helper_sees_advisory_500():
    start = QA.index("_API_CRASH_MARKERS")
    end = QA.index("\ndef _landing_skip_methodology_gate")
    ns: dict = {}
    exec("from __future__ import annotations\n" + QA[start:end], ns)
    journey = {
        "issues": [
            "demo_journey_5xx:/api/advisory:500:Internal Server Error",
            "demo_journey_5xx_cause: TypeError: get_advisory() got an unexpected keyword argument 'args'",
        ]
    }
    assert ns["_journey_has_api_crash"](journey)
    visual = {"issues": ["a11y_missing_h1", "spec_alignment_llm_failed:blank"]}
    assert not ns["_journey_has_api_crash"](visual)


def test_import_error_boot_failure_is_an_api_crash():
    """Otherwise SPA pages fill the six while main.py cannot import auth."""
    start = QA.index("_API_CRASH_MARKERS")
    end = QA.index("\ndef _landing_skip_methodology_gate")
    ns: dict = {}
    exec("from __future__ import annotations\n" + QA[start:end], ns)
    journey = {
        "issues": [
            "backend_boot_failed:uvicorn_failed_to_listen: ImportError: cannot import name 'auth'",
            "demo_journey_boot_failed:uvicorn_failed_to_listen: ImportError: cannot import name 'auth' from 'app.routers'",
            "import_error: ImportError: cannot import name 'auth' from 'app.routers'  (app/main.py:7)",
        ]
    }
    assert ns["_journey_has_api_crash"](journey)
