"""Incomplete input is its own class: not a provider miss, and not a refusal.

The hub scores ``ok`` against ``fail`` and nothing else. A call that arrived without
the coordinates a capability needs is traffic, so it keeps its row, gets its own mark
(``incomplete``) and its own counter, and never moves the success rate.
"""

import pytest

from aimarket_hub.invoke_outcome import (
    classify_invoke_outcome,
    reads_as_incomplete_input,
    scored_success_rate,
)


@pytest.mark.parametrize(
    "reason",
    [
        # Every one of these is a live reply, copied from the satellites on 2026-09-16.
        "lat/lon required (lat −90…90, lon −180…180)",          # atlas.nearest.read@v1
        "provide watchbox_id or west/south/east/north + layers",  # atlas.watchbox.check@v1
        "west/south/east/north bbox required",                   # atlas.situation.brief@v1
        "point_id required",
        "unknown watchbox: wb-7",
        "no valid layers",
        "field `since` is required",
        "missing required parameter: cell",
        "invalid coordinates",
    ],
)
def test_peer_input_complaints_are_incomplete(reason):
    assert classify_invoke_outcome(delivered=False, refuse_reason=reason) == "incomplete"


@pytest.mark.parametrize(
    "reason",
    [
        # "required" appears in all of these and none of them is a malformed request:
        # laundering them into the unscored bucket would hide real misses.
        "payment required — send X-API-Key",
        "authorization required",
        "api key required",
        "rate limit exceeded",
        "quota exhausted for this plan",
        "channel balance too low",
        "upstream timeout after 30s",
        "sensor offline, no coverage in bbox",
    ],
)
def test_decisions_and_misses_are_not_incomplete(reason):
    assert classify_invoke_outcome(delivered=False, refuse_reason=reason) == "fail"


def test_schema_required_fields_are_enough_without_a_reason():
    assert classify_invoke_outcome(
        delivered=False,
        refuse_reason="",
        input_payload={},
        input_schema={"required": ["lat", "lon"]},
    ) == "incomplete"


def test_present_fields_fall_through_to_the_reason():
    assert classify_invoke_outcome(
        delivered=False,
        refuse_reason="sensor offline",
        input_payload={"lat": 55.7, "lon": 37.6},
        input_schema={"required": ["lat", "lon"]},
    ) == "fail"


def test_delivered_is_ok_whatever_else_is_set():
    assert classify_invoke_outcome(
        delivered=True, refuse_reason="lat/lon required",
    ) == "ok"


def test_empty_reason_is_a_miss_not_an_excuse():
    assert not reads_as_incomplete_input("")
    assert classify_invoke_outcome(delivered=False, refuse_reason="") == "fail"


def test_success_rate_ignores_both_unscored_classes():
    assert scored_success_rate(ok=9, fail=1, refused=0, incomplete=0) == pytest.approx(0.9)
    assert scored_success_rate(ok=9, fail=1, refused=5, incomplete=40) == pytest.approx(0.9)


def test_success_rate_with_only_unscored_traffic_is_perfect():
    assert scored_success_rate(ok=0, fail=0, incomplete=12) == 1.0
    assert scored_success_rate(ok=0, fail=0, refused=3) == 1.0


def test_success_rate_with_nothing_at_all_is_zero():
    assert scored_success_rate(ok=0, fail=0) == 0.0


def test_gaia_needs_a_place_is_incomplete():
    """GAIA's reply to an empty call; it scored 29 empty MCP probes as failed reads."""
    reason = ('gaia.weather.read needs a place: latitude and longitude, or city (e.g. "Tokyo"), '
              'or an exact device_id. The demo-site simulator answers only to device_id=ws-01.')
    assert classify_invoke_outcome(delivered=False, refuse_reason=reason) == "incomplete"


@pytest.mark.parametrize("reason", ["the relay needs a restart", "GAIA needs a moment"])
def test_needs_a_something_else_is_still_a_miss(reason):
    assert classify_invoke_outcome(delivered=False, refuse_reason=reason) == "fail"


@pytest.mark.parametrize(
    "reason",
    [
        # Live replies, 2026-10-04: a point with no sensor near it is an answer about the
        # world, not a failure of ours, and must not move the success rate.
        "no LIVE readings within 2500 km for layers ['weather']",
        "no live weather relay within 75 km of Tokyo; the nearest is om-wx-01 at 8900 km "
        "— pass device_id=om-wx-01 to read it anyway",
    ],
)
def test_no_coverage_near_the_place_is_refused_not_failed(reason):
    assert classify_invoke_outcome(delivered=False, refuse_reason=reason) == "refused"


@pytest.mark.parametrize(
    "reason",
    [
        "upstream timeout after 30s",
        "GAIA relay down: no live response within 10 s",   # still ours: a dead upstream
        "payment required: no live channel within budget",
    ],
)
def test_infrastructure_failures_stay_scored(reason):
    assert classify_invoke_outcome(delivered=False, refuse_reason=reason) != "refused"
