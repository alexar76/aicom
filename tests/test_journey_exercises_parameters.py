"""An endpoint asked only to refuse has not been tested.

The demo journey swept "every parameterless GET" and treated anything under 500 as fine. A
weather product's single public feature is ``GET /api/advisory?lat=&lon=``; the sweep called it
bare, got the 422 for the missing arguments, and recorded that as correct. The real call —

    TypeError: get_advisory() missing 1 required positional argument: 'request'

— returns 500 and was never made. The product went through roughly ninety developer/QA rounds
with its only feature broken, because nothing in the pipeline ever asked it to do its job.

So required parameters are now filled from the endpoint's own OpenAPI schema. Two properties
matter and both are pinned here: the values must be ones the endpoint should accept (a
latitude of 1 is legal but lands in the ocean, where an honest hazard product returns nothing
and the 500 stays hidden), and a 422 *after* supplying schema-derived values is itself a
finding — the app is rejecting a caller who followed its own documented contract.
"""

from __future__ import annotations

import pytest

from web.backend.services.product_demo_journey import _required_query, _sample_query_value


def test_required_query_parameters_are_filled():
    op = {
        "parameters": [
            {"name": "lat", "in": "query", "required": True, "schema": {"type": "number"}},
            {"name": "lon", "in": "query", "required": True, "schema": {"type": "number"}},
            {"name": "units", "in": "query", "required": False, "schema": {"type": "string"}},
        ]
    }
    query = _required_query(op)
    assert set(query) == {"lat", "lon"}, "optional parameters must not be invented"


def test_coordinates_land_somewhere_with_data():
    """The exact reason this is not "just send 1".

    lat=1, lon=1 is valid and sits in the Gulf of Guinea, where a hazard product legitimately
    has no readings — so the endpoint answers "nothing here" and a 500 further in never fires.
    """
    for name in ("lat", "latitude"):
        assert _sample_query_value({"name": name, "schema": {"type": "number"}}) == 52.52
    for name in ("lon", "lng", "longitude"):
        assert _sample_query_value({"name": name, "schema": {"type": "number"}}) == 13.40


def test_the_schema_is_respected_over_guessing():
    assert _sample_query_value({"name": "mode", "schema": {"enum": ["live", "sim"]}}) == "live"
    assert _sample_query_value({"name": "n", "schema": {"type": "integer", "default": 7}}) == 7
    # A declared range is honoured: sending 1 into minimum=10 gets a legitimate refusal that
    # looks exactly like the defect this sweep is meant to find.
    assert _sample_query_value(
        {"name": "limit", "schema": {"type": "integer", "minimum": 10, "maximum": 20}}
    ) == 15
    assert _sample_query_value({"name": "since", "schema": {"type": "integer", "minimum": 3}}) == 3


@pytest.mark.parametrize(
    "schema,expected_type",
    [
        ({"type": "string"}, str),
        ({"type": "number"}, (int, float)),
        ({"type": "integer"}, int),
        ({}, str),
    ],
)
def test_a_value_is_produced_for_every_declared_type(schema, expected_type):
    """No parameter shape may yield None: a missing value re-creates the bare call."""
    value = _sample_query_value({"name": "whatever", "schema": schema})
    assert value is not None
    assert isinstance(value, expected_type)


def test_no_parameters_means_no_query_string():
    """Endpoints that need nothing must keep being called exactly as before."""
    assert _required_query({}) == {}
    assert _required_query({"parameters": []}) == {}
    assert _required_query({"parameters": "malformed"}) == {}


def test_path_and_header_parameters_are_not_sent_as_query():
    op = {
        "parameters": [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
            {"name": "X-Token", "in": "header", "required": True, "schema": {"type": "string"}},
            {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
        ]
    }
    assert _required_query(op) == {"q": "test"}


def test_rejecting_its_own_schema_is_reported_as_a_defect():
    """Structural: a 422 after supplying schema-derived values must become an issue.

    Otherwise the sweep swaps one blind spot for another — it would send the right arguments
    and then accept the refusal, which is how the bare call hid the 500 in the first place.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "web" / "backend" / "services" / "product_demo_journey.py"
    text = src.read_text(encoding="utf-8")
    assert "demo_journey_rejects_own_schema" in text
    assert "status == 422 and query" in text
    # And the call itself must carry the query string.
    assert "url += \"?\" + urlencode(query)" in text
