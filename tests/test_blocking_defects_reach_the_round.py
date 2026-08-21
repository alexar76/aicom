"""The prioritisation machinery existed and was fed nothing.

``agents/dev.py`` builds two things a repair round badly needs, with a comment saying exactly
why: ``fix_these_first_they_break_the_build`` (from ``quality_gates.blocking_defects``) and
``only_edit_these_paths`` (from ``quality_gates.repair_scope``) — because the raw gate dump
"puts cosmetic findings (contrast, empty states) alongside 'the app does not compile'".

Both were unreachable. The task-input builder in ``orchestrator/task_executor_agent.py``
assembles ``quality_gates_feedback`` from a hand-picked list of keys, and neither of those two
was in it. So every round received a flat list, and the measurement showed what that costs: of
15 findings handed to one round, **6 were cosmetic** (missing skeleton, empty state, error UI,
toast, responsive nav) while the product's only public feature returned no data at all.

Separately, the three detectors added for defects that stop the product working —
``duplicate_tablename`` (the app never boots), ``route_handler_broken_injection`` (permanent
500 on that route), ``mesh_contract_violation`` (200 with no data forever) — were reported as
critical but were **not** in ``blocking_defects``, so even a working passthrough would have
ranked them beside a loading skeleton.

These tests pin both halves, because either one alone leaves the round blind.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_keys_dev_reads_are_passed_through():
    """The exact defect: the consumer reads two keys the producer never sent."""
    dev = (ROOT / "agents" / "dev.py").read_text(encoding="utf-8")
    # What dev.py reads out of the gates payload.
    assert '.get("blocking_defects")' in dev
    assert '.get("repair_scope")' in dev

    executor = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    subset_start = executor.index('"quality_gates_feedback": {')
    subset = executor[subset_start : subset_start + 2000]
    assert '"blocking_defects"' in subset, (
        "blocking_defects is not passed to the round, so fix_these_first is never built"
    )
    assert '"repair_scope"' in subset, (
        "repair_scope is not passed, so the round may rewrite the half that already passes"
    )


def test_the_detector_gates_are_passed_through():
    """A round that cannot see module_health cannot fix what only it detects."""
    executor = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    subset_start = executor.index('"quality_gates_feedback": {')
    subset = executor[subset_start : subset_start + 2000]
    for gate in ("module_health", "frontend_build", "api_contract", "demo_journey"):
        assert f'"{gate}"' in subset, f"{gate} findings never reach the round"


def test_defects_that_stop_the_product_are_ranked_as_blocking():
    """Critical severity is not enough — ranking is what the round acts on first."""
    qa = (ROOT / "agents" / "qa.py").read_text(encoding="utf-8")
    head = qa[: qa.index("# Deletions next")]
    for code in (
        "duplicate_tablename",
        "route_handler_broken_injection",
        "mesh_contract_violation",
    ):
        assert code in head, (
            f"{code} is not in blocking_defects, so a round ranks it beside a loading skeleton"
        )


def test_they_come_before_the_pre_existing_blocking_codes():
    """Nothing else can matter while the app does not boot at all."""
    qa = (ROOT / "agents" / "qa.py").read_text(encoding="utf-8")
    boot = qa.index("duplicate_tablename")
    symbols = qa.index('i.get("code") == "missing_symbol"')
    assert boot < symbols, (
        "missing symbols are ranked above 'the app never boots', which is backwards: with two "
        "models on one table there is no app to have symbols in"
    )


def test_dev_still_explains_why_scope_is_restricted():
    """A scope limit without a reason reads as arbitrary and gets ignored."""
    dev = (ROOT / "agents" / "dev.py").read_text(encoding="utf-8")
    assert "only_edit_these_paths" in dev
    assert "wastes the round" in dev, "the round is not told why the limit exists"


# --- the scope has to be enforceable, not just emitted -----------------------------------


def test_a_file_level_scope_allows_that_file(tmp_path):
    """The bug this test exists for would have made every round land empty.

    Enforcement built prefixes as ``entry + "/"``, so an exact file entry became
    "…atlas_client.py/" and matched nothing — every write, including the one file the scope
    was meant to permit, would have been reverted. QA now emits file-level scopes whenever the
    blocking defects name few enough files, so this is load-bearing.
    """
    from agents.dev import _revert_out_of_scope_writes

    code = tmp_path / "code"
    (code / "backend" / "app" / "services").mkdir(parents=True)
    allowed = "backend/app/services/atlas_client.py"
    other = "frontend/src/App.tsx"
    (code / allowed).write_text("new\n", encoding="utf-8")
    (code / "frontend" / "src").mkdir(parents=True)
    (code / other).write_text("new\n", encoding="utf-8")

    reverted = _revert_out_of_scope_writes(
        code,
        {allowed: "old\n", other: "old\n"},
        [allowed, other],
        [allowed],
        log=lambda *a, **k: None,
        product_id="prod-x",
    )
    assert allowed not in reverted, "the file the scope names was reverted"
    assert other in reverted, "a write outside the scope was kept"
    assert (code / allowed).read_text(encoding="utf-8") == "new\n"
    assert (code / other).read_text(encoding="utf-8") == "old\n"


def test_a_directory_scope_still_works(tmp_path):
    """The pre-existing half-of-the-tree behaviour must not regress."""
    from agents.dev import _revert_out_of_scope_writes

    code = tmp_path / "code"
    (code / "backend" / "app").mkdir(parents=True)
    (code / "frontend" / "src").mkdir(parents=True)
    inside, outside = "backend/app/main.py", "frontend/src/App.tsx"
    for rel in (inside, outside):
        (code / rel).write_text("new\n", encoding="utf-8")

    reverted = _revert_out_of_scope_writes(
        code, {inside: "old\n", outside: "old\n"}, [inside, outside], ["backend/"],
        log=lambda *a, **k: None, product_id="prod-x",
    )
    assert reverted == {outside}


def test_the_file_scope_stays_small():
    """A scope naming thirty files is not a scope, and must not pretend to be one.

    Originally enforced by refusing to emit anything above six files, which turned out to leave
    the scope empty exactly when it was needed — a round with twelve critical findings names more
    than six files. The bound is now kept by truncation instead, so this asserts the property
    (never more than six) rather than the condition that used to produce it.
    """
    qa = (ROOT / "agents" / "qa.py").read_text(encoding="utf-8")
    assert "blocking_files[:6]" in qa, (
        "an unbounded file scope lets a sprawling round call itself surgical"
    )
    assert "blocking_files" in qa
    # And the coarse half-of-the-tree fallback must remain for when findings name no files.
    assert 'repair_scope = ["frontend/"]' in qa


def test_the_scope_truncates_instead_of_giving_up():
    """All-or-nothing left the scope empty exactly when it mattered most.

    A round with 12 critical/high findings names more than six files, so the old rule emitted
    no limit at all and the round spread over ~20 files in six unfocused batches — the very
    situation the limit exists for. The issues arrive ranked with the product-does-not-run codes
    first, so truncating keeps what is worth a round and the tail follows once these land.
    """
    qa = (ROOT / "agents" / "qa.py").read_text(encoding="utf-8")
    assert "repair_scope = blocking_files[:6]" in qa, (
        "the scope still refuses to emit anything above six files"
    )
    assert "if 0 < len(blocking_files) <= 6" not in qa, "the all-or-nothing rule is still there"
    assert "Repair scope truncated" in qa, (
        "a silently truncated scope hides that later findings are deferred"
    )
