import json
from pathlib import Path

from core.playbook import distill, load_rules, retrieve_rules


def _ep(category, *, shipped, ev, signal=""):
    return {
        "category": category,
        "objective": {"shipped": shipped, "ev": ev},
        "root_cause": {"signal": signal},
    }


def _seed(data_root: Path, episodes):
    fp = data_root / "state" / "episodes.jsonl"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("\n".join(json.dumps(e) for e in episodes) + "\n", encoding="utf-8")


def test_distill_promotes_positive_lift_rule(tmp_path):
    # 4 good shipped builds, 3 failed builds sharing one defect signal.
    episodes = [_ep("saas", shipped=True, ev=2.4) for _ in range(4)]
    episodes += [_ep("saas", shipped=False, ev=-1.3, signal="missing pricing block") for _ in range(3)]
    _seed(tmp_path, episodes)

    active = distill(tmp_path)
    assert active == 1

    rules = load_rules(tmp_path)
    rule = next(r for r in rules if r["status"] == "active")
    assert rule["claim"] == "avoid: missing pricing block"
    assert rule["lift_ev"] > 0  # avoiding the defect measurably raises EV
    assert rule["scope"]["category"] == "saas"


def test_distill_retires_when_signal_does_not_hurt(tmp_path):
    # Defect signal appears but builds with it are not worse → no active rule.
    episodes = [_ep("devtools", shipped=True, ev=1.0) for _ in range(3)]
    episodes += [_ep("devtools", shipped=False, ev=5.0, signal="cosmetic nit") for _ in range(3)]
    _seed(tmp_path, episodes)

    distill(tmp_path)
    rules = load_rules(tmp_path)
    assert all(r["status"] != "active" for r in rules)


def test_retrieve_returns_only_scope_matched_active_rules(tmp_path):
    episodes = [_ep("saas", shipped=True, ev=2.0) for _ in range(4)]
    episodes += [_ep("saas", shipped=False, ev=-1.0, signal="broken auth") for _ in range(3)]
    _seed(tmp_path, episodes)
    distill(tmp_path)

    assert retrieve_rules(tmp_path, category="saas")  # matches
    assert retrieve_rules(tmp_path, category="unrelated") == []  # different category


def test_distill_empty_is_noop(tmp_path):
    assert distill(tmp_path) == 0
