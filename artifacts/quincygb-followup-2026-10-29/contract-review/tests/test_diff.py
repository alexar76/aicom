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


def _with_contract(score, output_fields):
    return _result(
        schema_quality={"score": score, "contract": {"output": output_fields}}
    )


_CONTRACT_V1 = {"$": "object", "$ (required)": "amount,unit", "$.amount": "string", "$.unit": "string"}
_CONTRACT_V2 = {"$": "object", "$ (required)": "amount,unit", "$.amount": "number", "$.unit": "string"}


def test_field_type_flip_is_contract_change_with_stable_score():
    # The aicom case (2026-10-29): an output field flips string ->
    # number; both schema scores stay 100. The diff must report a
    # contract change, not "no changes".
    d = compute_diff(_with_contract(100, _CONTRACT_V1), _with_contract(100, _CONTRACT_V2))
    assert d["contract_stability"] == "changed"
    assert d["schema_score_stability"] == "stable"
    contract_changes = [c for c in d["changes"] if c.get("kind") == "contract_change"]
    assert len(contract_changes) == 1
    entry = contract_changes[0]
    assert entry["path"] == "$.amount"
    assert entry["before"] == "string"
    assert entry["after"] == "number"
    assert "no changes" not in d["summary"]


def test_identical_contract_is_stable():
    d = compute_diff(_with_contract(100, _CONTRACT_V1), _with_contract(100, dict(_CONTRACT_V1)))
    assert d["contract_stability"] == "stable"
    assert d["changes"] == []
    assert d["summary"].startswith("no changes since")


def test_legacy_results_without_contract_report_unknown():
    d = compute_diff(_result(), _with_contract(100, _CONTRACT_V1))
    assert d["contract_stability"] == "unknown"
    assert [c for c in d["changes"] if c.get("kind") == "contract_change"] == []


def test_contract_field_added_and_removed():
    before = {"$": "object", "$.a": "string", "$.gone": "number"}
    after = {"$": "object", "$.a": "string", "$.new": "boolean"}
    d = compute_diff(_with_contract(100, before), _with_contract(100, after))
    assert d["contract_stability"] == "changed"
    kinds = {(c["path"], c["before"], c["after"]) for c in d["changes"]}
    assert ("$.gone", "number", None) in kinds
    assert ("$.new", None, "boolean") in kinds


def test_score_change_without_contract_change():
    d = compute_diff(_with_contract(90, _CONTRACT_V1), _with_contract(100, _CONTRACT_V1))
    assert d["schema_score_stability"] == "changed"
    assert d["contract_stability"] == "stable"
    assert [c["field"] for c in d["changes"]] == ["schema_score"]
