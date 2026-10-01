"""A round is judged whole, and that is why good work kept being thrown away.

Measured twice in six minutes, on a tree that had finally reached zero static defects:

    Applied 9 edit(s) across 6 file(s): advisory.ts, Dashboard.tsx, AnalyticsDashboard.tsx,
                                        PublicWidget.tsx, test_cache.py, test_atlas_client.py
    Rejected: what moved — missing_attribute 0→1 | added: missing_attribute: atlas_client.invoke
    Rejected: static defects would rise 0 → 10; tree restored

Three of those edits were the three tsc errors the round had been sent to fix. They score **nothing**
in this measure — type errors come from an npm build, far too slow to run twice per round — while the
one backend attribute the round broke scores ten. So a round doing exactly the work it was asked for
could not come out ahead, and the frontend could never be fixed by a round that touched the backend
at all.

Reverting file by file, keeping each revert only while it helps, salvages what was right. The
alternative was to make the score see tsc, which costs minutes per round; this costs one static pass
per candidate file and only on a round that would otherwise be discarded.
"""

from __future__ import annotations

from pathlib import Path

from agents.dev import _revert_until_not_worse

QUIET = lambda *a, **k: None  # noqa: E731


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_only_the_file_that_broke_something_is_given_back(tmp_path):
    """The live shape: good frontend edits kept, the one bad backend edit returned.

    The breaking file used to be `routers/advisory.py` here. It cannot be any more:
    `_revert_until_not_worse` now refuses to hand back mesh wiring
    (`routers/advisory.py`, `services/atlas_client.py`, the participant modules),
    because giving those back kept undoing the product's reason to exist and the next
    round rediscovered `capability_never_invoked`. Pinning the old expectation made this
    test assert the exact behaviour the function was changed to stop doing — see
    `test_mesh_wiring_is_never_given_back` below for that rule.
    """
    code = tmp_path / "code"
    _tree(
        code,
        {
            # The breakage: reads an attribute the class does not declare.
            "backend/app/routers/reports.py": (
                "from ..services.report_client import ReportClient\n\n"
                "report_client = ReportClient()\n"
                "x = report_client.render('a')\n"
            ),
            "backend/app/services/report_client.py": (
                "class ReportClient:\n    def render_report(self, c):\n        return {}\n"
            ),
            # The good work: type-level only, invisible to this score.
            "frontend/src/api/advisory.ts": "export const get = () => 1\n",
            "frontend/src/pages/AnalyticsDashboard.tsx": "export const P = () => null\n",
        },
    )
    previous = {
        "backend/app/routers/reports.py": (
            "from ..services.report_client import ReportClient\n\n"
            "report_client = ReportClient()\n"
            "x = report_client.render_report('a')\n"
        ),
        "frontend/src/api/advisory.ts": "export const old = () => 0\n",
        "frontend/src/pages/AnalyticsDashboard.tsx": "export const Old = () => null\n",
    }

    given_back = _revert_until_not_worse(
        code,
        previous,
        list(previous),
        before_score=0,
        log=QUIET,
        product_id="prod-x",
        already=set(),
    )

    assert given_back == {"backend/app/routers/reports.py"}, given_back
    # The frontend work survives.
    assert "export const get" in (code / "frontend/src/api/advisory.ts").read_text(encoding="utf-8")
    # And the tree is no longer worse than it was.
    from agents.dev import _tree_defect_score

    assert (_tree_defect_score(code) or 0) <= 0


def test_mesh_wiring_is_never_given_back(tmp_path):
    """Rejecting the whole round beats undoing the product's reason to exist.

    Salvage kept handing back `routers/advisory.py` / `services/atlas_client.py`
    because unrelated static noise outweighed the invoke edge, and the next round
    rediscovered `capability_never_invoked`.
    """
    code = tmp_path / "code"
    _tree(
        code,
        {
            "backend/app/routers/advisory.py": (
                "from ..services.atlas_client import AtlasClient\n\n"
                "atlas_client = AtlasClient()\n"
                "x = atlas_client.invoke('a')\n"
            ),
            "backend/app/services/atlas_client.py": (
                "class AtlasClient:\n    def invoke_capability(self, c):\n        return {}\n"
            ),
        },
    )
    previous = {
        "backend/app/routers/advisory.py": (
            "from ..services.atlas_client import AtlasClient\n\n"
            "atlas_client = AtlasClient()\n"
            "x = atlas_client.invoke_capability('a')\n"
        ),
    }

    assert _revert_until_not_worse(
        code,
        previous,
        list(previous),
        before_score=0,
        log=QUIET,
        product_id="prod-x",
        already=set(),
    ) == set()
    # Untouched: the round is rejected as a whole elsewhere, not silently unwired here.
    assert "atlas_client.invoke(" in (
        code / "backend/app/routers/advisory.py"
    ).read_text(encoding="utf-8")


def test_a_round_that_is_already_fine_gives_nothing_back(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/main.py": "x = 1\n"})
    assert _revert_until_not_worse(
        code, {"backend/app/main.py": "x = 0\n"}, ["backend/app/main.py"],
        before_score=5, log=QUIET, product_id="prod-x", already=set(),
    ) == set()


def test_a_file_already_reverted_is_not_touched_again(tmp_path):
    code = _tree(tmp_path / "code", {"backend/app/main.py": "from .gone import x\n"})
    given_back = _revert_until_not_worse(
        code, {"backend/app/main.py": "y = 1\n"}, ["backend/app/main.py"],
        before_score=0, log=QUIET, product_id="prod-x", already={"backend/app/main.py"},
    )
    assert given_back == set()


def test_a_new_file_that_broke_the_tree_is_removed(tmp_path):
    """A round may introduce a file, not only change one."""
    code = _tree(
        tmp_path / "code",
        {
            "backend/app/main.py": "y = 1\n",
            "backend/app/bad.py": "from .nowhere import thing\n",
        },
    )
    given_back = _revert_until_not_worse(
        code, {"backend/app/main.py": "y = 1\n"}, ["backend/app/main.py", "backend/app/bad.py"],
        before_score=0, log=QUIET, product_id="prod-x", already=set(),
    )
    assert given_back == {"backend/app/bad.py"}
    assert not (code / "backend" / "app" / "bad.py").exists()


def test_the_answer_is_the_same_every_time(tmp_path):
    """Greedy order must be deterministic or one round gives two answers."""
    answers = set()
    for i in range(3):
        code = tmp_path / f"code{i}"
        _tree(
            code,
            {
                "backend/app/a.py": "from .nowhere import x\n",
                "backend/app/b.py": "from .nowhere import y\n",
                "backend/app/c.py": "z = 1\n",
            },
        )
        answers.add(
            frozenset(
                _revert_until_not_worse(
                    code,
                    {"backend/app/a.py": "p = 1\n", "backend/app/b.py": "q = 1\n", "backend/app/c.py": "z = 0\n"},
                    ["backend/app/c.py", "backend/app/a.py", "backend/app/b.py"],
                    before_score=0, log=QUIET, product_id="prod-x", already=set(),
                )
            )
        )
    assert len(answers) == 1, answers


def test_it_runs_only_after_the_cheaper_surgical_revert():
    """Structural: the undefined-name pass is cheaper and more specific, so it goes first."""
    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    region = src[src.index("if patch_mode and before_score is not None:") :][:5000]
    assert region.index("_revert_files_with_new_undefined_names") < region.index(
        "_revert_until_not_worse"
    )
    assert "salvaged" in region
