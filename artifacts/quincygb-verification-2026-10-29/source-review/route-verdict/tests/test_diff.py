"""Offline tests for the pure diff computation."""

from app.checker import compute_diff


def _result(**over):
    base = {
        "checked_at": "2026-10-21T00:00:00+00:00",
        "liveness": {"alive": True},
        "terms": {
            "amount_units": "20000",
            "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "pay_to": "0x1111111111111111111111111111111111111111",
            "network": "eip155:8453",
        },
        "schema_quality": {"score": 100},
        "catalog": {
            "cdp_bazaar": {"status": "listed"},
            "payai": {"status": "not_listed"},
        },
    }
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def test_no_prior_check():
    d = compute_diff(None, _result())
    assert d["prior_check"] is False
    assert d["changes"] == []
    assert d["summary"] == "no prior check on record"


def test_identical_checks_report_no_changes():
    d = compute_diff(_result(), _result(checked_at="2026-10-22T00:00:00+00:00"))
    assert d["prior_check"] is True
    assert d["changes"] == []
    assert d["summary"].startswith("no changes since")


def test_multiple_changes_all_reported():
    prior = _result()
    current = _result(
        terms={"amount_units": "99000", "pay_to": "0x2222222222222222222222222222222222222222"},
        schema_quality={"score": 40},
        catalog={"payai": {"status": "listed"}},
    )
    d = compute_diff(prior, current)
    fields = {c["field"] for c in d["changes"]}
    assert fields == {"price", "pay_to", "schema_score", "payai_listing"}
    assert d["prior_checked_at"] == "2026-10-21T00:00:00+00:00"
    assert "4 change(s)" in d["summary"]


def test_liveness_flip_is_a_change():
    d = compute_diff(_result(), _result(liveness={"alive": False}))
    assert {c["field"] for c in d["changes"]} == {"liveness"}
