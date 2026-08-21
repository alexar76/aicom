"""Fewer criticals is progress even when the weighted total rises.

Measured at the end of a long repair. A round was reverted at 14 -> 15 — one severity point — having
closed two of the three missing attributes and introduced one lesser finding. Discarding it threw away
both fixes to avoid the one, the next round started from the same tree and made the same trade, and
that ran sixty-six times.

A critical is what stops the product working: a missing symbol, an attribute never declared, a broken
mesh contract. The smaller findings a round leaves behind are the next round's work — refusing the
trade refuses both halves.
"""

from __future__ import annotations

from pathlib import Path

from core.round_regression_guard import critical_pressure

ROOT = Path(__file__).resolve().parents[1]


def _bug(sev: str, title: str) -> dict:
    return {"severity": sev, "title": title, "file": f"{title[:6]}.py"}


def test_it_counts_criticals_from_trusted_gates_only():
    bugs = [
        _bug("critical", "Module health: missing_attribute"),
        _bug("critical", "Module health: missing_symbol"),
        _bug("high", "Module health: unstyled_classes"),
        _bug("critical", "Browser E2E: spec_alignment_llm_failed"),   # untrusted gate
        _bug("critical", "Insecure default secret_key"),              # ungated opinion
    ]
    assert critical_pressure({"bugs_found": bugs}) == 2


def test_no_opinion_when_there_is_nothing_to_read():
    assert critical_pressure({}) is None
    assert critical_pressure("nope") is None
    assert critical_pressure({"bugs_found": []}) == 0


def test_the_guard_accepts_a_round_that_lowered_the_criticals():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "crits = critical_pressure(qa_result)" in guard
    assert "crits < stored_crits" in guard
    assert "or fewer_criticals" in guard, "it must feed the same accept branch as a breakthrough"
    assert "the criticals fell" in guard, "a silent acceptance hides why the total was overruled"


def test_a_round_that_raises_the_criticals_gets_no_exemption():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert "crits < stored_crits" in guard and "crits <= stored_crits" not in guard


def test_a_dead_backend_still_wins_over_a_lower_critical_count():
    """Order matters: a product that does not start has no qualities to measure, whatever the count."""
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    assert guard.index("boots is False and was_booting is True") < guard.index(
        "fewer_criticals"
    )


def test_the_state_survives_sqlite():
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_critical_pressure" in PRODUCT_EXTRA_KEYS


def test_the_baseline_comes_from_the_re_measured_tree_not_the_stored_context():
    """Derived from the wrong place first, and the wrong place was silent about it.

    The stored accepted context holds the LLM reviewer's half of the diagnosis — 25 findings on the
    live product, not one of them carrying a gate prefix — so measuring it recorded a baseline of 0
    while the tree had three critical missing attributes. An axis with a zero baseline can never fire.
    The re-measured static findings for the restored tree are the only place those criticals exist.
    """
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert 'critical_pressure({"bugs_found": accepted_ctx.get("qa_findings") or []})' in guard
    assert guard.index("_refresh_static_findings(accepted_ctx") < guard.index(
        '_base_crits = critical_pressure('
    ), "measure after the re-measurement, or the gate findings are not there yet"
    assert "measured on the restored tree" in guard


def test_the_baseline_is_derived_when_it_was_never_recorded():
    """The axis fired never, because its baseline was only written on accept paths.

    On a product whose every round reverts — sixty-seven in a row here — last_critical_pressure stayed
    None, so `crits < stored_crits` was False forever and the new axis changed nothing. The accepted
    diagnosis travels with the tree being kept, so the baseline can be measured from it instead of
    waiting for an acceptance that the axis itself was supposed to enable.
    """
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    guard = guard[: guard.index("def _refresh_static_findings(")]
    assert "last_critical_pressure" in guard
    assert "_base_crits" in guard, "some path must establish the baseline without an acceptance"


def test_the_derivation_happens_before_the_comparison():
    src = (ROOT / "orchestrator" / "task_executor_agent.py").read_text(encoding="utf-8")
    guard = src[src.index("def _guard_round_regression(") :]
    # The boot-loss branch reverts earlier and needs no baseline; what matters is that the derivation
    # precedes the ORDINARY revert, where the accepted diagnosis is still the one in hand.
    assert guard.index("_base_crits = critical_pressure(") > guard.rindex(
        "restore_snapshot(pid, code_root, host.data_root)"
    ), "the tree must be restored and re-measured before its criticals are counted"
