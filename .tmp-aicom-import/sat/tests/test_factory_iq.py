import json
from pathlib import Path

from core.factory_iq import factory_iq_snapshot


def _seed_episodes(data_root: Path, episodes):
    fp = data_root / "state" / "episodes.jsonl"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("\n".join(json.dumps(e) for e in episodes) + "\n", encoding="utf-8")


def _ep(ev, *, shipped=True, frozen=False, cost=0.2):
    return {
        "category": "saas",
        "learning_frozen": frozen,
        "objective": {"shipped": shipped, "ev": ev, "cost_usd": cost},
        "root_cause": {"signal": ""},
    }


def test_snapshot_empty_is_safe(tmp_path):
    snap = factory_iq_snapshot(tmp_path)
    assert snap["factory_iq"] is not None
    assert snap["builds"] == {"live": 0, "frozen": 0}
    assert snap["learning_curve"]["gap"] is None


def test_learning_curve_gap_reflects_live_vs_frozen(tmp_path):
    # Live cohort improving, frozen control flat & lower.
    episodes = [_ep(0.5, frozen=True) for _ in range(4)]
    episodes += [_ep(0.4) for _ in range(3)] + [_ep(2.0) for _ in range(3)]  # live rises
    _seed_episodes(tmp_path, episodes)

    snap = factory_iq_snapshot(tmp_path)
    lc = snap["learning_curve"]
    assert lc["frozen_ev_mean"] == 0.5
    assert lc["live_ev_mean"] > lc["frozen_ev_mean"]
    assert lc["gap"] > 0 and lc["paying_off"] is True
    assert snap["ev_slope"] > 0  # second half better than first → improving
    assert 0.0 <= snap["factory_iq"] <= 100.0


def test_ship_rate_and_cost(tmp_path):
    episodes = [_ep(1.0, shipped=True, cost=0.3), _ep(-1.0, shipped=False, cost=0.5)]
    _seed_episodes(tmp_path, episodes)
    snap = factory_iq_snapshot(tmp_path)
    assert snap["ship_rate"] == 0.5
    assert snap["cost_per_ship"] == 0.8  # total live cost / shipped count
