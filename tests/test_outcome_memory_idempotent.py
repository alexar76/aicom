from pathlib import Path

from core.outcome_memory import outcomes_path, episodes_path, record_terminal_outcome


def _count_lines(fp: Path) -> int:
    return len(fp.read_text(encoding="utf-8").splitlines()) if fp.is_file() else 0


def test_record_terminal_outcome_is_idempotent(tmp_path: Path):
    """Monitoring cycles re-invoke record_terminal_outcome for products that stay
    COMPLETED; it must record the terminal outcome exactly once (no duplicate
    outcome/episode rows, no repeated bandit reward)."""
    root = tmp_path / "data"
    product = {
        "id": "prod-idem",
        "state": "COMPLETED",
        "category": "saas",
        "tags": ["x"],
        "config_arm": "arm-A",
    }

    record_terminal_outcome(root, product)
    record_terminal_outcome(root, product)  # simulated monitoring re-run
    record_terminal_outcome(root, product)

    assert _count_lines(outcomes_path(root)) == 1
    assert _count_lines(episodes_path(root)) == 1


def test_distinct_terminal_states_each_record_once(tmp_path: Path):
    root = tmp_path / "data"
    record_terminal_outcome(root, {"id": "p1", "state": "FAILED", "category": "c"})
    record_terminal_outcome(root, {"id": "p1", "state": "FAILED", "category": "c"})
    # A later COMPLETED terminal state for the same id is a distinct outcome.
    record_terminal_outcome(root, {"id": "p1", "state": "COMPLETED", "category": "c"})

    assert _count_lines(outcomes_path(root)) == 2
