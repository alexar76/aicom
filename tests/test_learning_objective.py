from core.learning_objective import (
    assign_learning_cohort,
    cohort_is_frozen,
    demand_value,
    expected_value,
    frozen_cohort_fraction,
    learning_ab_enabled,
    learning_frozen,
)


def test_demand_value_zero_without_traffic():
    assert demand_value({}) == 0.0
    assert demand_value(None) == 0.0


def test_demand_value_weights_invokes_highest():
    v = demand_value({"aimarket_invokes": 10, "views": 0, "checkout_starts": 0})
    assert v == 10 * 0.50


def test_expected_value_failed_build_is_cost_only_negative():
    ev = expected_value(shipped=False, cost_usd=1.0, repair_rounds=2, demand={"aimarket_invokes": 99})
    # No value credited when not shipped; cost + repair penalty make it negative.
    assert ev < 0
    assert ev == round(-(1.0 + 2 * 0.10), 4)


def test_expected_value_shipped_with_demand_is_positive():
    ev = expected_value(shipped=True, cost_usd=0.5, repair_rounds=0, demand={"aimarket_invokes": 4})
    assert ev == round(4 * 0.50 - 0.5, 4)
    assert ev > 0


def test_learning_ab_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AIFACTORY_LEARNING_FROZEN", raising=False)
    monkeypatch.delenv("AIFACTORY_LEARNING_AB", raising=False)
    assert learning_ab_enabled() is False
    assert learning_frozen() is False
    assert cohort_is_frozen("prod-any") is False


def test_learning_ab_master_switch_enables_split(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LEARNING_FROZEN", "1")
    monkeypatch.delenv("AIFACTORY_LEARNING_FROZEN_FRACTION", raising=False)
    assert learning_ab_enabled() is True
    assert frozen_cohort_fraction() == 0.5
    assert learning_frozen() is False  # 50/50 split — not all-frozen without product


def test_learning_frozen_all_frozen_when_fraction_one(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LEARNING_FROZEN", "1")
    monkeypatch.setenv("AIFACTORY_LEARNING_FROZEN_FRACTION", "1")
    assert learning_frozen() is True
    assert cohort_is_frozen("prod-x") is True


def test_assign_learning_cohort_is_stable(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LEARNING_FROZEN", "1")
    monkeypatch.setenv("AIFACTORY_LEARNING_FROZEN_FRACTION", "0.5")
    p = {"id": "prod-stable-cohort"}
    a = assign_learning_cohort(p)
    b = assign_learning_cohort({"id": "prod-stable-cohort"})
    assert a == b
    assert p["learning_frozen"] == a
    assert learning_frozen(p) == a


def test_ab_split_produces_both_cohorts(monkeypatch):
    monkeypatch.setenv("AIFACTORY_LEARNING_FROZEN", "1")
    monkeypatch.setenv("AIFACTORY_LEARNING_FROZEN_FRACTION", "0.5")
    frozen = {assign_learning_cohort({"id": f"prod-ab-{i}"}) for i in range(40)}
    assert True in frozen
    assert False in frozen
