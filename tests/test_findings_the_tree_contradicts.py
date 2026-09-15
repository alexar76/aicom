"""A round cannot create a file that already exists, so a finding claiming it is missing is immortal.

Measured live on a product down to four defects. An LLM finding read:

    GITHUB_HOUSE_CONTRACT not satisfied: missing required repository files
    No README.md, LICENSE, CHANGELOG.md, docs/, docs/badges/, .github/workflows/ci.yml, or
    .github/workflows/release.yml were provided. These are mandatory for full_software products.

All seven were in the tree. Rounds that tried to satisfy it wrote files that were already there —
and were then reverted as out-of-scope sprawl, which is how one hallucination consumed a whole
evening's worth of rounds while a blocking gate stayed red.
"""

from __future__ import annotations

from pathlib import Path

from agents.qa import QAAgent


def _tree(root: Path, rels: list[str]) -> Path:
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    return root


HOUSE = {
    "severity": "high",
    "title": "GITHUB_HOUSE_CONTRACT not satisfied: missing required repository files",
    "description": (
        "No README.md, LICENSE, CHANGELOG.md, docs/, docs/badges/, .github/workflows/ci.yml, or "
        ".github/workflows/release.yml were provided. These are mandatory for full_software."
    ),
}


def test_a_claim_of_absence_every_path_of_which_exists_is_dropped(tmp_path):
    code = _tree(
        tmp_path / "code",
        ["README.md", "LICENSE", "CHANGELOG.md", "docs/en.md", "docs/badges/ci.svg",
         ".github/workflows/ci.yml", ".github/workflows/release.yml"],
    )
    kept = QAAgent._drop_findings_the_tree_contradicts([HOUSE], code, log=lambda *a, **k: None)
    assert kept == []


def test_a_partly_true_claim_survives_narrowed_to_what_is_missing(tmp_path):
    code = _tree(
        tmp_path / "code",
        ["README.md", "CHANGELOG.md", "docs/en.md", "docs/badges/ci.svg",
         ".github/workflows/ci.yml", ".github/workflows/release.yml"],
    )  # LICENSE genuinely absent
    kept = QAAgent._drop_findings_the_tree_contradicts([HOUSE], code, log=lambda *a, **k: None)
    assert len(kept) == 1
    assert "only LICENSE" in kept[0]["description"]
    assert "actually missing" in kept[0]["description"]


def test_findings_that_are_not_about_absence_are_untouched(tmp_path):
    code = _tree(tmp_path / "code", ["backend/app/routers/auth.py"])
    bugs = [
        {"severity": "high", "title": "browser_http_500:POST /api/auth/login:500",
         "description": "the handler for this route lives in backend/app/routers/auth.py"},
        {"severity": "high", "title": "CSRF protection implementation incomplete",
         "description": "tokens are generated but never validated"},
    ]
    assert QAAgent._drop_findings_the_tree_contradicts(bugs, code, log=lambda *a, **k: None) == bugs


def test_an_incomplete_repo_claim_is_dropped_when_both_halves_exist(tmp_path):
    """LLM saw ten truncated attachments and said the repository was missing modules.

    app/main.py in the finding is the truncated path of backend/app/main.py, so the
    absence filter kept it (that exact relpath is not on disk) and it filled the
    round while contrast was the only real leftover.
    """
    code = _tree(
        tmp_path / "code",
        ["backend/app/main.py", "frontend/src/App.tsx"],
    )
    bugs = [
        {
            "severity": "critical",
            "title": "Provided repository is incomplete / missing modules",
            "description": "The archive only contains app/main.py",
            "file": "app/main.py",
        }
    ]
    kept = QAAgent._drop_findings_the_tree_contradicts(bugs, code, log=lambda *a, **k: None)
    assert kept == []
    """"No clear CTA detected" is about content, not files — the filter must not touch it."""
    code = _tree(tmp_path / "code", ["index.html"])
    bugs = [{"severity": "high", "title": "ux_missing_cta",
             "description": "No clear CTA/button detected; conversion path is unclear."}]
    assert QAAgent._drop_findings_the_tree_contradicts(bugs, code, log=lambda *a, **k: None) == bugs


def test_the_filter_runs_before_the_scope_and_the_score():
    """Filtered after scoping, a phantom would still pull an innocent file into the repair scope;
    filtered after scoring, it would still count against the round in the ratchet."""
    qa = (Path(__file__).resolve().parents[1] / "agents" / "qa.py").read_text(encoding="utf-8")
    filtered = qa.index("all_bugs = self._drop_findings_the_tree_contradicts(")
    scope = qa.index("blocking_files: list[str] = []")
    score = qa.index("release_score = self._compute_release_score(")
    assert filtered < scope < score


def test_a_measured_finding_is_never_filtered(tmp_path):
    """A detector that READ the tree cannot be contradicted by the tree — it is the tree's report.

    Learned one round after the filter shipped. `orm_schema_never_created` says "migrations exist
    (backend/alembic/versions/0001_initial.py) but nothing runs alembic upgrade", which mentions
    files that do exist — and the filter dropped the one finding that had correctly diagnosed a
    database with no schema at all. Two fixes, each right on its own, cancelling each other out.
    """
    code = _tree(tmp_path / "code", ["backend/alembic/versions/0001_initial.py", "Dockerfile",
                                     "backend/app/main.py"])
    measured = {
        "severity": "critical",
        "title": "Module health: orm_schema_never_created",
        "description": (
            "16 tables are declared and NOTHING creates them at runtime: migrations exist "
            "(backend/alembic/versions/0001_initial.py) but no Dockerfile, compose file, "
            "entrypoint or startup hook ever runs `alembic upgrade`. Fix it in "
            "backend/app/main.py."
        ),
    }
    kept = QAAgent._drop_findings_the_tree_contradicts([measured], code, log=lambda *a, **k: None)
    assert kept == [measured]


def test_every_measured_prefix_is_spared(tmp_path):
    code = _tree(tmp_path / "code", ["README.md"])
    bugs = [
        {"title": f"{prefix} something about README.md missing", "description": "no README.md"}
        for prefix in ("Module health:", "API contract:", "Browser E2E:", "Demo journey:",
                       "Demo/TZ gate:", "Frontend build:", "Backend runtime:")
    ]
    assert QAAgent._drop_findings_the_tree_contradicts(bugs, code, log=lambda *a, **k: None) == bugs


def test_a_truncated_claim_against_a_file_that_parses_is_dropped(tmp_path):
    """LLM review of a truncated attachment is not a syntax error in the product.

    Sentinel round 50: 'Incomplete rate_limit decorator causes syntax error' and
    'app/main.py appears truncated' while both files parsed. Those two criticals then
    sat above the real compile and 401 defects.
    """
    code = tmp_path / "code"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "deps.py").write_text(
        "def rate_limit(times, seconds):\n    def decorator(func):\n        return func\n    return decorator\n",
        encoding="utf-8",
    )
    bug = {
        "severity": "critical",
        "title": "Incomplete rate_limit decorator causes syntax error",
        "description": "The rate_limit decorator in app/deps.py is truncated after @wraps.",
        "file": "app/deps.py",
        "source": "llm_review",
    }
    kept = QAAgent._drop_findings_the_tree_contradicts([bug], code, log=lambda *a, **k: None)
    assert kept == []


def test_a_truncated_claim_against_a_file_that_does_not_parse_is_kept(tmp_path):
    code = tmp_path / "code"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "main.py").write_text("def broken(\n", encoding="utf-8")
    bug = {
        "severity": "critical",
        "title": "app/main.py appears truncated",
        "description": "The main application file is cut off mid-code.",
        "file": "app/main.py",
        "source": "llm_review",
    }
    kept = QAAgent._drop_findings_the_tree_contradicts([bug], code, log=lambda *a, **k: None)
    assert kept == [bug]


def test_llm_cookie_auth_is_dropped_when_the_journey_already_named_the_401(tmp_path):
    """Two findings, one defect. The measured one says how the client authenticates."""
    code = tmp_path / "code"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "backend" / "app" / "deps.py").write_text("x = 1\n", encoding="utf-8")
    bugs = [
        {
            "severity": "high",
            "title": "Demo journey: demo_journey_auth_rejected:/api/analytics/dashboards:401",
            "description": "This client authenticates ONLY via Authorization: Bearer.",
            "file": "backend/app/deps.py",
        },
        {
            "severity": "medium",
            "title": "Authentication only reads cookie token",
            "description": "get_current_user in app/deps.py reads the token from request.cookies",
            "file": "app/deps.py",
            "source": "llm_review",
        },
    ]
    kept = QAAgent._drop_findings_the_tree_contradicts(bugs, code, log=lambda *a, **k: None)
    assert len(kept) == 1
    assert "auth_rejected" in kept[0]["title"]
