"""Offline tests for the Bazaar schema-quality scorer.

Pins the hollow detector: {"type", "example"}-only outputs (87.8% of the
catalog) must be flagged hollow with named deductions; fully typed
schemas must score clean.
"""

from app.schema_quality import evaluate_schema_quality

FULL_EXT = {
    "info": {
        "input": {
            "type": "http",
            "method": "POST",
            "bodyType": "json",
            "body": {"q": "example"},
        },
        "output": {
            "type": "json",
            "example": {"verdict": "OK", "score": 12},
            "schema": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string"},
                    "score": {"type": "number"},
                },
            },
        },
    }
}


def test_no_extension_scores_none():
    q = evaluate_schema_quality(None, "desc")
    assert q["extension_present"] is False
    assert q["hollow"] is None
    assert q["score"] is None
    assert q["deductions"] == []


def test_full_schema_scores_100():
    q = evaluate_schema_quality(FULL_EXT, "Short description.")
    assert q["extension_present"] is True
    assert q["hollow"] is False
    assert q["score"] == 100
    assert q["deductions"] == []


def test_hollow_type_example_only():
    ext = {
        "info": {
            "input": {"type": "http", "method": "POST", "bodyType": "json", "body": {}},
            "output": {"type": "json", "example": {"anything": 1}},
        }
    }
    q = evaluate_schema_quality(ext, "desc")
    assert q["hollow"] is True
    names = [d["name"] for d in q["deductions"]]
    assert "hollow output (example only, no schema)" in names
    assert q["score"] == 55  # 100 - 45


def test_missing_output_is_hollow():
    ext = {"info": {"input": {"type": "http", "body": {"x": 1}}}}
    q = evaluate_schema_quality(ext, "desc")
    assert q["hollow"] is True
    assert any(d["name"] == "output section missing" for d in q["deductions"])


def test_schema_with_no_typed_fields_is_hollow():
    ext = {
        "info": {
            "input": {"type": "http", "body": {"x": 1}},
            "output": {
                "type": "json",
                "example": {},
                "schema": {"type": "object"},
            },
        }
    }
    q = evaluate_schema_quality(ext, "desc")
    assert q["hollow"] is True
    assert any(d["name"] == "output schema types no real fields" for d in q["deductions"])


def test_untyped_properties_deduct_but_not_hollow():
    ext = {
        "info": {
            "input": {"type": "http", "body": {"x": 1}},
            "output": {
                "type": "json",
                "example": {},
                "schema": {
                    "type": "object",
                    "properties": {"a": {"type": "string"}, "b": {}},
                },
            },
        }
    }
    q = evaluate_schema_quality(ext, "desc")
    assert q["hollow"] is False
    assert q["score"] == 95
    assert q["deductions"][0]["name"] == "untyped output properties"


def test_long_description_deducts():
    q = evaluate_schema_quality(FULL_EXT, "x" * 501)
    assert any(d["name"] == "description over 500 characters" for d in q["deductions"])
    assert q["score"] == 90


def test_missing_description_deducts():
    q = evaluate_schema_quality(FULL_EXT, None)
    assert any(d["name"] == "no resource description" for d in q["deductions"])


def test_schema_contract_captures_field_types():
    from app.schema_quality import schema_contract

    contract = schema_contract(FULL_EXT)
    assert contract == {
        "output": {"$": "object", "$.score": "number", "$.verdict": "string"}
    }


def test_schema_contract_distinguishes_type_flip_at_equal_quality():
    from app.schema_quality import schema_contract

    flipped = {
        "info": {
            "input": FULL_EXT["info"]["input"],
            "output": {
                "type": "json",
                "example": {"verdict": "OK", "score": 12},
                "schema": {
                    "type": "object",
                    "properties": {
                        "verdict": {"type": "string"},
                        "score": {"type": "string"},
                    },
                },
            },
        }
    }
    # Both extensions score 100 — quality is unchanged — but the
    # contracts differ, which is the distinction the diff relies on.
    assert evaluate_schema_quality(FULL_EXT, "desc")["score"] == 100
    assert evaluate_schema_quality(flipped, "desc")["score"] == 100
    assert schema_contract(FULL_EXT) != schema_contract(flipped)
    assert schema_contract(flipped)["output"]["$.score"] == "string"


def test_schema_contract_none_without_typed_schema():
    from app.schema_quality import schema_contract

    assert schema_contract(None) is None
    assert schema_contract({"info": {"output": {"type": "json", "example": {}}}}) is None
