"""A gate that gets sharper must be allowed to reconsider what it already passed.

Measured end to end in one hour. A product reached nine green gates, published to Vercel, and was
marked COMPLETED. Then two new detectors landed and found, in that same shipped tree:

* `import jwt` with no PyJWT behind it — every API route on the live deployment answered
  FUNCTION_INVOCATION_FAILED;
* 47 Tailwind utility classes in a product with no Tailwind — the page rendered as unstyled HTML.

Both critical, both true, and nothing looked at them: COMPLETED is terminal, and the verdict that
produced it was measured under rules that could not see either defect. Without this sweep every
detector improvement applies only to products built afterwards, and everything already shipped keeps
its defects permanently.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "orchestrator" / "task_queue_hygiene.py").read_text(encoding="utf-8")
BODY = SRC[SRC.index("def reopen_completed_with_critical_defects(") : SRC.index("def unpark_budget_exhausted(")]


def test_only_finished_products_are_candidates():
    assert 'state not in ("COMPLETED", "SALES_ACTIVE")' in BODY


def test_only_critical_defects_reopen_a_product():
    """A medium duplicate-module note must never drag a shipped product back into repair."""
    assert 'i.get("severity") == "critical"' in BODY


def test_it_reopens_at_most_once_per_rules_version():
    """Otherwise a detector that keeps firing spins the pipeline forever."""
    assert "_REOPENED_FOR_RULES" in SRC
    assert "== SCORING_RULES_VERSION" in BODY
    assert 'product["last_reopen_rules_version"] = SCORING_RULES_VERSION' in BODY


def test_a_clean_shipped_product_is_marked_and_left_alone():
    """No criticals: record the version so the sweep stops measuring it every pass."""
    start = BODY.index("if not criticals:")
    clean = BODY[start : BODY.index("codes = sorted(", start)]
    assert 'product["last_reopen_rules_version"] = SCORING_RULES_VERSION' in clean
    assert 'product["state"] = "BUG_FOUND"' not in clean


def test_the_reopen_says_why():
    assert "Reopening %s from %s" in BODY
    assert "sharper detectors" in BODY
    assert '", ".join(codes)' in BODY, "the log must name which detectors fired"


def test_the_repair_counter_restarts():
    """A reopened product gets a fresh budget of rounds; the old count belongs to the old verdict."""
    assert 'product["quality_repair_round"] = 0' in BODY


def test_it_runs_in_the_worker_loop():
    worker = (ROOT / "pipeline_worker.py").read_text(encoding="utf-8")
    assert "reopen_completed_with_critical_defects(products)" in worker
    assert worker.index("unpark_budget_exhausted(products)") < worker.index(
        "reopen_completed_with_critical_defects(products)"
    ), "unpark first: a parked product is not a shipped one"


def test_the_key_survives_the_sqlite_round_trip():
    from orchestrator.product_extras import PRODUCT_EXTRA_KEYS

    assert "last_reopen_rules_version" in PRODUCT_EXTRA_KEYS
