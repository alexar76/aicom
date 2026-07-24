import random

from core.process_bandit import arm_stats, default_arms, select_arm, select_process_arm, update


def test_default_arms():
    assert "balanced" in default_arms()


def test_update_and_arm_stats(tmp_path):
    update(tmp_path, category="saas", arm="heavy", reward=2.0)
    update(tmp_path, category="saas", arm="heavy", reward=4.0)
    update(tmp_path, category="saas", arm="light", reward=-1.0)
    stats = arm_stats(tmp_path, "saas")
    assert stats["heavy"]["n"] == 2
    assert stats["heavy"]["mean_ev"] == 3.0
    assert stats["light"]["mean_ev"] == -1.0


def test_select_arm_prefers_winner_without_exploration(tmp_path, monkeypatch):
    for _ in range(20):
        update(tmp_path, category="saas", arm="heavy", reward=5.0)
        update(tmp_path, category="saas", arm="light", reward=-5.0)
    monkeypatch.setenv("AIFACTORY_LEARNING_EXPLORE_FRAC", "0.0")  # pure exploit
    random.seed(1)
    picks = [select_arm(tmp_path, category="saas", arms=["heavy", "light"]) for _ in range(15)]
    assert picks.count("heavy") > picks.count("light")


def test_select_process_arm_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFACTORY_PROCESS_BANDIT", raising=False)
    assert select_process_arm(tmp_path, "saas") is None
    monkeypatch.setenv("AIFACTORY_PROCESS_BANDIT", "1")
    assert select_process_arm(tmp_path, "saas") in default_arms()
