"""A repair round goes out in short bursts, because asking nicely was already tried.

The developer prompt asks for only the changed files and carries the measurement that justifies
it — "~80 files emitted to fix five findings, the overwhelming majority byte-identical to what
was already on disk" — and ``patch_mode`` adds "prefer minimal targeted edits instead of full
rewrites". Both are requests. A round whose work list named three files wrote about eighty-five,
measured 128 severity-weighted against a baseline of 41, and was thrown away; seven consecutive
rounds went that way with the baseline never moving.

The output cap is 128k tokens, so eighty-five files *fit* — truncation was not the cause, and
sharpening the prose further would not have helped either. What the round cannot argue with is a
per-batch allowance: a call sized for three files cannot return a tree.

What these tests pin is mostly ordering and containment, because that is where batching either
pays for itself or quietly makes things worse: the defects that stop the product working must
lead (a later batch is worthless if the app never boots), and a batch must not be able to pull
the round back into rewriting everything.
"""

from __future__ import annotations

import pytest

from core.repair_batches import (
    batch_instruction,
    batch_max_tokens,
    batch_size,
    batching_enabled,
    plan_batches,
)

BOOT_BLOCKER = {
    "severity": "critical",
    "code": "duplicate_tablename",
    "title": "Module health: duplicate_tablename",
    "detail": "backend/app/models/advisory.py and backend/app/models/audit.py both declare invoke_audit_logs",
}
DEAD_MESH = {
    "severity": "critical",
    "code": "mesh_contract_violation",
    "title": "Module health: mesh_contract_violation",
    "detail": "backend/app/services/atlas_client.py sends capability instead of capability_id",
}
COSMETIC = {
    "severity": "high",
    "title": "Demo/TZ gate: visual_app_missing_skeleton",
    "detail": "frontend/src/App.tsx has no loading skeleton",
}
COMPILE = {
    "severity": "high",
    "title": "Frontend build: frontend_build_failed: frontend/src/pages/PublicWidget.tsx(54,35): error TS2322",
    "detail": "Type 'HazardInfo' is not assignable to type 'Hazard' in frontend/src/pages/PublicWidget.tsx",
}
AUTH_401 = {
    "severity": "high",
    "title": "Demo journey: demo_journey_auth_rejected:/api/analytics/dashboards:401",
    "detail": "backend/app/deps.py must accept Authorization: Bearer alongside the cookie",
}
FILELESS = {"severity": "low", "title": "Cache service unit test is shallow", "detail": "no path"}


def test_defects_that_stop_the_product_are_attempted_first():
    """A skeleton in batch one is a batch wasted while the app does not boot.

    Ordering is the whole reason batching helps rather than merely splits: if the last batch
    fails or times out, the round should still have landed the fixes that matter.
    """
    batches = plan_batches([COSMETIC, BOOT_BLOCKER, DEAD_MESH], size=1)
    first_files = batches[0]["files"]
    assert any("models" in f for f in first_files), batches
    assert not any("App.tsx" in f for f in first_files), "cosmetics led the round"


def test_a_landing_html_finding_enters_the_batch():
    """Visual gates file against index.html; without that path in the batch the round
    cannot edit it, and the out-of-scope guard reverts the landing. Sentinel 56."""
    landing = {
        "severity": "high",
        "title": "Demo/TZ gate: root_absolute_paths",
        "detail": "code/prod-x/index.html uses absolute /… asset URLs",
        "file": "index.html",
    }
    batches = plan_batches([landing, COSMETIC], size=2)
    named = [f for b in batches for f in b["files"]]
    assert any(f.endswith("index.html") for f in named), named


def test_compile_and_auth_rejected_lead_visual_cosmetics():
    """Same severity, different outcome. Sentinel rounds 49–51 spent themselves on operator
    Dashboard.tsx (high, like everything else) while PublicWidget.tsx still did not typecheck
    and deps.py still read only the cookie. Ranking is the mechanism; asking the prompt to
    'fix 401 first' was already tried."""
    batches = plan_batches([COSMETIC, COMPILE, AUTH_401], size=1)
    first = " ".join(batches[0]["files"])
    assert "PublicWidget.tsx" in first or "deps.py" in first, batches
    assert "App.tsx" not in first, "a missing skeleton led the round ahead of compile/401"


def test_findings_are_grouped_by_file_within_the_size_limit():
    batches = plan_batches([BOOT_BLOCKER, DEAD_MESH, COSMETIC], size=2)
    assert len(batches) == 2
    assert all(len(b["files"]) <= 2 for b in batches), batches
    # Every finding survives the split; a batching scheme that drops work is worse than none.
    assert sum(len(b["findings"]) for b in batches) == 3


def test_a_finding_naming_no_file_gets_its_own_final_batch():
    """It has to go somewhere, and putting it first lets a vague finding rewrite the tree."""
    batches = plan_batches([FILELESS, BOOT_BLOCKER])
    assert batches[-1]["files"] == []
    assert batches[-1]["findings"] == [FILELESS]
    assert batches[0]["files"], "the file-bearing finding must lead"


def test_a_file_scope_confines_the_plan():
    """When QA named the files, a batch must not reach outside them."""
    batches = plan_batches(
        [BOOT_BLOCKER, DEAD_MESH, COSMETIC],
        scope=["backend/app/services/atlas_client.py"],
    )
    named = [f for b in batches for f in b["files"]]
    assert named == ["backend/app/services/atlas_client.py"], named


def test_no_findings_means_no_batching():
    """An initial build needs one coherent pass; batching it produces files that never met."""
    assert plan_batches([]) == []


def test_the_batch_instruction_names_only_its_own_files_and_says_why():
    batches = plan_batches([BOOT_BLOCKER, DEAD_MESH], size=1)
    text = batch_instruction(batches[0], 0, len(batches))
    assert "BATCH 1 OF 2" in text
    assert "backend/app/models/advisory.py" in text
    assert "atlas_client" not in text, "a batch was told about another batch's file"
    assert "eighty-five" in text, (
        "the instruction should carry the measurement; a bare 'be minimal' is what failed"
    )


def test_batching_focuses_the_round_it_does_not_ration_the_answer():
    """Corrected premise. This test used to assert the output allowance was a small fraction of the
    heavy budget, on the theory that a large allowance makes batching pointless. Those are two
    different mechanisms, and conflating them cost a round: a batch rewriting three whole files hit a
    24k ceiling, the third file came back stopping mid-def, and the round was reverted for the
    SyntaxError that created.

    What makes a batch a batch is FILE FOCUS — few files, named findings. The answer should be as long
    as the model can make it, taken from that model's own configuration."""
    from core.repair_batches import active_model_limits

    assert batch_size() <= 5, "focus is the mechanism"
    model_max = active_model_limits().get("max_tokens") or 0
    if model_max:
        assert batch_max_tokens() >= model_max, "do not ask for less than the model will give"


@pytest.mark.parametrize("value,expected", [("0", False), ("false", False), ("1", True)])
def test_batching_can_be_turned_off(monkeypatch, value, expected):
    monkeypatch.setenv("AIFACTORY_REPAIR_BATCHING", value)
    assert batching_enabled() is expected


def test_the_runner_skips_a_failed_batch_instead_of_losing_the_round():
    """Structural: one transient non-JSON response used to cost a twenty-minute round."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    runner = src[src.index("async def _generate_repair_batches") :]
    runner = runner[: runner.index("\n    async def execute(")]
    assert "continue" in runner, "a failed batch aborts the round"
    assert "returned no usable JSON; skipping it" in runner
    assert "batch_max_tokens()" in runner, "the batch call does not use the small allowance"
    # A later batch must be able to supersede an earlier one for the same file.
    assert "merged[path] = item" in runner


def test_the_unscoped_batch_is_told_its_ceiling():
    """Measured on the first live batched rounds: 19 and 21 files from the unscoped batch while
    its scoped siblings returned 3 and 1 — three quarters of the round, from the one batch
    nothing bounded. The token allowance does not bind it; 21 small files fit in 24k easily."""
    from core.repair_batches import unscoped_batch_max_files

    batches = plan_batches([FILELESS, BOOT_BLOCKER])
    text = batch_instruction(batches[-1], 1, 2)
    assert str(unscoped_batch_max_files()) in text
    assert "dropped, not reviewed" in text, "a silent drop reads as the model being ignored"


def test_the_cap_is_enforced_not_merely_requested():
    """Structural: the whole point of this module is limits the instruction cannot outrun."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    runner = src[src.index("async def _generate_repair_batches") :]
    runner = runner[: runner.index("\n    async def execute(")]
    assert "unscoped_batch_max_files()" in runner, "the cap is never applied at accept time"
    assert "limit is not None and wrote >= limit" in runner
    assert "dropped" in runner, "surplus files are dropped silently"
    # A scoped batch must NOT be capped by count — its paths already bound it.
    assert "None if (batch.get(\"files\") or []) else" in runner


def test_a_scoped_batch_keeps_all_its_files():
    """Capping a scoped batch by count would drop a legitimate fix that spans its own files."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "limit = None if (batch.get(\"files\") or []) else unscoped_batch_max_files()" in src


def test_a_bad_batch_is_dropped_before_it_joins_the_round():
    """The docstring promised damage one batch wide; it was a whole round wide.

    Observed live: six batches produced 21 files with 0% wasted output, and the round was then
    rejected in full — "static defects would rise 15 → 20" — discarding five good batches along
    with the one that broke something. The check is on the returned content rather than on disk,
    because writing inside the runner would make the main loop's rollback baseline the previous
    attempt's output, which is a trap the diagnosis already flagged.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agents" / "dev.py").read_text(encoding="utf-8")
    runner = src[src.index("async def _generate_repair_batches") :]
    runner = runner[: runner.index("\n    async def execute(")]
    assert "undefined_names_in_source" in runner, "a batch joins the round unchecked"
    assert "without binding or importing them" in runner, (
        "the drop is not explained, so the next attempt cannot avoid repeating it"
    )
    assert "the rest of the round is unaffected" in runner
    # It must not write to disk here.
    assert "write_text" not in runner, (
        "writing inside the runner poisons the main loop's rollback baseline"
    )


def test_the_content_check_distinguishes_broken_from_whole():
    """The analysis has to be real, or the drop is arbitrary."""
    from web.backend.services.duplicate_module_check import undefined_names_in_source

    broken = "def go():\n    return helper(x)\n"
    whole = "def helper(y):\n    return y\n\ndef go():\n    return helper(1)\n"
    assert undefined_names_in_source(broken), "a file using unbound names read as fine"
    assert undefined_names_in_source(whole) == [], "a correct file was flagged"


def test_a_directory_scope_binds_the_plan():
    """Directory scopes used to be dropped entirely, and the cost was a whole round.

    Scoped to ["frontend/"], the planner happily built batches out of BACKEND findings — the round
    edited three backend files and had every one reverted as out-of-scope. Work thrown away by
    construction.
    """
    frontend = {
        "severity": "high",
        "title": "Frontend build: frontend_build_failed",
        "detail": "frontend/src/pages/PublicWidget.tsx(49,19): error TS2345",
    }
    backend = {
        "severity": "high",
        "title": "Test failure",
        "detail": "backend/tests/integration/test_auth.py fails on fixture",
    }
    batches = plan_batches([frontend, backend], scope=["frontend/"])
    named = [f for b in batches for f in b["files"]]
    assert named == ["frontend/src/pages/PublicWidget.tsx"], named


def test_a_finding_entirely_outside_the_scope_leaves_the_plan():
    """Filtered-to-empty used to mean "fileless", which means "no path restriction".

    The backend finding under a frontend/ scope landed in the unscoped batch, and the round spent it
    editing backend files — every one reverted as out-of-scope. Out of scope must mean out of the
    plan; a genuinely file-less finding still rides along.
    """
    frontend = {
        "severity": "high",
        "title": "Frontend build: frontend_build_failed",
        "detail": "frontend/src/pages/PublicWidget.tsx(49,19): error TS2345",
    }
    backend = {
        "severity": "high",
        "title": "Test failure",
        "detail": "backend/tests/integration/test_auth.py fails on fixture",
    }
    vague = {"severity": "low", "title": "Docs are thin", "detail": "no file named here"}
    batches = plan_batches([frontend, backend, vague], scope=["frontend/"])
    all_findings = [f for b in batches for f in b["findings"]]
    assert backend not in all_findings, "an out-of-scope finding re-entered through the fileless batch"
    assert vague in all_findings, "a genuinely file-less finding was lost"
    assert [b["files"] for b in batches] == [["frontend/src/pages/PublicWidget.tsx"], []]


def test_a_finding_is_not_truncated_below_its_own_instruction():
    """The cut is what turned a full instruction into its opposite.

    A missing-attribute finding is 716 characters. The old 600-character cut kept the list of methods
    the class does declare (offset 297) and removed the sentence forbidding deletion of the call site,
    leaving "…or stop reading it" as the last thing the model read. It deleted the ATLAS invocation
    twice. At most 12 findings reach a batch, so a 3000-character allowance costs ~36 KB in the worst
    case and nothing in the realistic one, where findings run 600-900 characters.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "core" / "repair_batches.py").read_text(
        encoding="utf-8"
    )
    assert "detail[:" not in src, "a finding must reach the model whole"
    assert "findings_listing_budget()" in src, "the only limit is a budget on the whole listing"
    assert "not listed here" in src, "an omission must be announced, never silent"


def test_a_long_finding_survives_intact():
    """The whole point: no sentence of an executable instruction may be cut off."""
    from core.repair_batches import batch_instruction

    long_detail = (
        "AtlasClient never declares 'get_advisory'. " + "x" * 4000 +
        " Do NOT delete the call site to silence this — the call is what the product does."
    )
    text = batch_instruction(
        {"files": ["a.py"], "findings": [{"severity": "critical", "title": "T", "detail": long_detail}]},
        0,
        1,
    )
    assert "Do NOT delete the call site" in text, "the tail of the instruction was cut"
    assert long_detail in text


def test_the_listing_budget_announces_what_it_dropped():
    from core.repair_batches import batch_instruction, findings_listing_budget

    budget = findings_listing_budget()
    huge = "y" * (budget // 2 + 100)
    findings = [
        {"severity": "critical", "title": f"F{i}", "detail": huge} for i in range(6)
    ]
    text = batch_instruction({"files": ["a.py"], "findings": findings}, 0, 1)
    assert "not listed here" in text
    assert "nothing has been silently dropped" in text


def test_the_first_finding_is_never_dropped_by_the_budget():
    """Even a finding larger than the whole budget must reach the model: it is the round's work."""
    from core.repair_batches import batch_instruction, findings_listing_budget

    over = "z" * (findings_listing_budget() + 5000)
    text = batch_instruction(
        {"files": ["a.py"], "findings": [{"severity": "critical", "title": "Only", "detail": over}]},
        0,
        1,
    )
    assert over in text
