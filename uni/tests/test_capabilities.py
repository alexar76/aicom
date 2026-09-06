"""Every capability in the bubble, held to the same contract — plus known-value checks.

Two kinds of test here, and the second is the one that matters. The generic pass proves each
capability is well-formed: it runs, it is deterministic, it refuses rubbish with a message
rather than a traceback, and its answer survives a JSON round trip. That catches a broken
capability but not a WRONG one.

So the second half checks named results against values computed elsewhere — a distance
between two cities, a binomial probability, a PageRank vector with a closed form. A bubble
whose arithmetic is merely plausible would be the exact thing the realm is supposed not to
be: a stage set.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from uni.capabilities import CATALOGUES, load_all, load_catalogue  # noqa: E402

ALL = [(cat, cap) for cat in load_all() for cap in cat.capabilities]
IDS = [f"{cat.product_id}/{cap.capability_id}" for cat, cap in ALL]


class TestEveryCapabilityIsWellFormed:
    @pytest.mark.parametrize(("cat", "cap"), ALL, ids=IDS)
    def test_its_example_runs_and_round_trips_through_json(self, cat, cap):
        """An example that does not run is a capability nobody has ever called."""
        result = cap.run(dict(cap.example))
        assert result is not None
        encoded = json.dumps(result, ensure_ascii=False)
        assert json.loads(encoded) == result, "result does not survive JSON"

    @pytest.mark.parametrize(("cat", "cap"), ALL, ids=IDS)
    def test_it_is_deterministic(self, cat, cap):
        """Two calls with one input must agree, or nothing downstream can be verified —
        including the response signature, which is bound to the result."""
        assert cap.run(dict(cap.example)) == cap.run(dict(cap.example))

    @pytest.mark.parametrize(("cat", "cap"), ALL, ids=IDS)
    def test_an_empty_payload_is_refused_not_crashed(self, cat, cap):
        """The satellite maps ValueError to 400 and anything else to 500. A capability that
        raises TypeError on a missing field reports the caller's mistake as its own fault."""
        try:
            cap.run({})
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"raised {type(exc).__name__} instead of ValueError: {exc}")

    @pytest.mark.parametrize(("cat", "cap"), ALL, ids=IDS)
    def test_it_declares_a_usable_schema_and_price(self, cat, cap):
        assert cap.input_schema.get("type") == "object", "input schema must describe an object"
        assert cap.description and len(cap.description) > 20
        assert cap.capability_id.endswith("@v1")
        # The crawler skips a row priced outside [0, 1000] and clamps latency into range;
        # a capability that would be dropped at index time may as well not exist.
        assert 0 <= cap.price_usd <= 1000
        assert 0 < cap.p50_latency_ms <= 300_000

    def test_capability_ids_are_unique_within_a_catalogue(self):
        for cat in load_all():
            ids = [c.capability_id for c in cat.capabilities]
            assert len(ids) == len(set(ids)), f"{cat.product_id} has duplicate ids"

    def test_every_catalogue_loads_and_the_bubble_is_not_thin(self):
        total = sum(len(load_catalogue(n).capabilities) for n in CATALOGUES)
        # The live hub carries 99 federated capabilities. A bubble with a handful is
        # distinguishable from it at a glance, which is the whole thing this exists to fix.
        assert total >= 80, f"only {total} capabilities across the bubble"


class TestTheArithmeticIsActuallyRight:
    """Known values, computed independently of this code."""

    def _run(self, product: str, capability: str, payload: dict) -> dict:
        return load_catalogue(product).by_id[capability].run(payload)

    def test_london_to_paris_is_about_343_kilometres(self):
        out = self._run("horizon", "geo.distance@v1",
                        {"from": {"lat": 51.5074, "lon": -0.1278},
                         "to": {"lat": 48.8566, "lon": 2.3522}})
        assert 343.0 < out["kilometres"] < 344.5

    def test_a_marathon_in_kilometres(self):
        out = self._run("stoicheion", "units.convert@v1",
                        {"value": 26.2, "from": "mi", "to": "km"})
        assert out["value"] == pytest.approx(42.164, abs=0.001)

    def test_a_temperature_conversion_and_its_floor(self):
        assert self._run("stoicheion", "units.convert@v1",
                         {"value": 100, "from": "C", "to": "F"})["value"] == 212.0
        with pytest.raises(ValueError, match="absolute zero"):
            self._run("stoicheion", "units.convert@v1",
                      {"value": -500, "from": "C", "to": "K"})

    def test_binomial_matches_the_closed_form(self):
        out = self._run("psephos", "prob.binomial@v1",
                        {"trials": 20, "probability": 0.3, "successes": 6})
        expected = math.comb(20, 6) * 0.3 ** 6 * 0.7 ** 14
        assert out["pmf"] == pytest.approx(expected, rel=1e-9)
        assert out["mean"] == pytest.approx(6.0)

    def test_two_aces_in_five_cards(self):
        out = self._run("psephos", "prob.hypergeometric@v1",
                        {"population": 52, "successes_in_population": 4,
                         "draws": 5, "observed_successes": 2})
        expected = math.comb(4, 2) * math.comb(48, 3) / math.comb(52, 5)
        assert out["pmf"] == pytest.approx(expected, rel=1e-9)

    def test_pagerank_of_a_symmetric_cycle_is_uniform(self):
        out = self._run("diktyon", "graph.pagerank@v1", {
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"},
                      {"source": "c", "target": "a"}],
            "directed": True,
        })
        for value in out["pagerank"].values():
            assert value == pytest.approx(1 / 3, abs=1e-6)

    def test_pagerank_sums_to_one_even_with_a_dangling_node(self):
        """A sink leaks rank unless its mass is redistributed — the classic silent bug."""
        out = self._run("diktyon", "graph.pagerank@v1", {
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "sink"}],
            "directed": True,
        })
        assert sum(out["pagerank"].values()) == pytest.approx(1.0, abs=1e-6)

    def test_dijkstra_prefers_the_cheaper_route_not_the_shorter_one(self):
        out = self._run("diktyon", "graph.shortest-path@v1", {
            "edges": [{"source": "a", "target": "b", "weight": 1},
                      {"source": "b", "target": "d", "weight": 1},
                      {"source": "a", "target": "d", "weight": 10}],
            "source": "a", "target": "d", "directed": True,
        })
        assert out["path"] == ["a", "b", "d"]
        assert out["distance"] == 2

    def test_the_spanning_tree_takes_the_light_edges(self):
        out = self._run("diktyon", "graph.minimum-spanning-tree@v1", {
            "edges": [{"source": "a", "target": "b", "weight": 1},
                      {"source": "b", "target": "c", "weight": 5},
                      {"source": "a", "target": "c", "weight": 2}],
        })
        assert out["total_weight"] == 3
        assert out["spans_whole_graph"] is True

    def test_a_preference_cycle_has_no_condorcet_winner(self):
        out = self._run("psephos", "vote.condorcet@v1",
                        {"ballots": [["a", "b", "c"], ["b", "c", "a"], ["c", "a", "b"]]})
        assert out["condorcet_winner"] is None
        assert out["has_cycle"] is True
        assert out["winner"] in {"a", "b", "c"}  # Copeland still returns something usable

    def test_a_clear_condorcet_winner_is_found(self):
        out = self._run("psephos", "vote.condorcet@v1",
                        {"ballots": [["a", "b", "c"], ["a", "c", "b"], ["b", "a", "c"]]})
        assert out["condorcet_winner"] == "a"

    def test_borda_can_disagree_with_first_preferences(self):
        """b loses the plurality and wins the Borda count — the textbook case, and proof the
        count is doing something more than counting firsts."""
        out = self._run("psephos", "vote.borda@v1", {
            "ballots": [["a", "b", "c"], ["a", "b", "c"], ["c", "b", "a"], ["c", "b", "a"],
                        ["b", "c", "a"]],
        })
        assert out["winner"] == "b"

    def test_a_seeded_draw_is_reproducible_and_a_different_seed_is_not(self):
        entries = list(range(50))
        first = self._run("psephos", "draw.deterministic@v1",
                          {"entries": entries, "seed": "alpha", "winners": 5})
        again = self._run("psephos", "draw.deterministic@v1",
                          {"entries": entries, "seed": "alpha", "winners": 5})
        other = self._run("psephos", "draw.deterministic@v1",
                          {"entries": entries, "seed": "beta", "winners": 5})
        assert first["winners"] == again["winners"]
        assert first["winners"] != other["winners"]
        assert len(set(first["winners"])) == 5, "a draw without replacement repeated an entry"

    def test_a_commitment_detects_a_changed_entry_list(self):
        commitment = self._run("psephos", "draw.commit@v1",
                               {"entries": ["a", "b"], "seed": "s"})["commitment"]
        honest = self._run("psephos", "draw.verify-commitment@v1",
                           {"entries": ["a", "b"], "seed": "s", "commitment": commitment})
        tampered = self._run("psephos", "draw.verify-commitment@v1",
                             {"entries": ["a", "b", "c"], "seed": "s", "commitment": commitment})
        assert honest["valid"] is True
        assert tampered["valid"] is False

    def test_the_draw_is_not_biased_toward_low_indices(self):
        """Rejection sampling, not modulo. A modulo bias is invisible in any single draw and
        is exactly how a lottery becomes quietly unfair."""
        counts = [0] * 5
        for i in range(600):
            out = self._run("psephos", "draw.deterministic@v1",
                            {"entries": [0, 1, 2, 3, 4], "seed": f"seed-{i}", "winners": 1})
            counts[out["winners"][0]] += 1
        assert min(counts) > 80, f"draw looks biased: {counts}"

    def test_the_dominant_frequency_of_a_known_tone(self):
        rate, freq = 64, 8
        series = [math.sin(2 * math.pi * freq * t / rate) for t in range(rate)]
        out = self._run("kyma", "signal.dominant-frequency@v1",
                        {"series": series, "sample_rate_hz": rate})
        assert out["dominant_frequency_hz"] == pytest.approx(freq, abs=0.5)

    def test_a_pure_tone_is_more_tonal_than_an_alternating_mess(self):
        rate = 64
        tone = [math.sin(2 * math.pi * 8 * t / rate) for t in range(rate)]
        noise = [((i * 2654435761) % 1000) / 500 - 1 for i in range(rate)]
        tonal = self._run("kyma", "signal.spectral-entropy@v1", {"series": tone})
        messy = self._run("kyma", "signal.spectral-entropy@v1", {"series": noise})
        assert tonal["normalised"] < messy["normalised"]

    def test_cross_correlation_recovers_a_known_delay(self):
        base = [0, 0, 1, 4, 1, 0, 0, 0]
        delayed = [0, 0, 0, 0, 1, 4, 1, 0]
        out = self._run("kyma", "signal.cross-correlation-lag@v1", {"a": base, "b": delayed})
        assert out["best_lag"] == 2

    def test_a_median_filter_removes_an_impulse_a_mean_would_smear(self):
        out = self._run("kyma", "signal.median-filter@v1",
                        {"series": [1, 1, 99, 1, 1], "window": 3})
        assert out["filtered"] == [1, 1, 1, 1, 1]

    def test_regression_recovers_a_known_line(self):
        out = self._run("khronos", "series.linear-regression@v1",
                        {"series": [3, 5, 7, 9, 11], "forecast": 1})
        assert out["slope"] == pytest.approx(2.0)
        assert out["intercept"] == pytest.approx(3.0)
        assert out["r_squared"] == pytest.approx(1.0)
        assert out["forecast"] == [13.0]

    def test_mad_finds_the_spike_that_a_mean_would_hide(self):
        out = self._run("khronos", "series.outliers-mad@v1",
                        {"series": [1, 2, 1, 2, 1, 2, 40]})
        assert [o["index"] for o in out["outliers"]] == [6]

    def test_autocorrelation_separates_the_period_from_the_strongest_dependence(self):
        """An alternating series correlates -0.875 at lag 1 and +0.75 at lag 2. The strongest
        dependence is the negative one; the PERIOD is the positive one. A single
        "strongest lag" field answers whichever question the caller did not ask."""
        out = self._run("khronos", "series.autocorrelation@v1",
                        {"series": [1, 2, 1, 2, 1, 2, 1, 2], "max_lag": 4})
        assert out["strongest_lag"] == 1
        assert out["acf"]["1"] < 0
        assert out["strongest_positive_lag"] == 2
        assert out["acf"]["2"] == pytest.approx(0.75, abs=0.05)

    def test_describe_matches_hand_computed_moments(self):
        out = self._run("khronos", "series.describe@v1", {"series": [2, 4, 4, 4, 5, 5, 7, 9]})
        assert out["mean"] == 5.0
        assert out["stdev"] == pytest.approx(2.13809, abs=1e-4)  # sample, n-1
        assert out["median"] == 4.5

    def test_gaps_are_filled_linearly_and_the_ends_are_held_flat(self):
        out = self._run("khronos", "series.interpolate-gaps@v1",
                        {"series": [None, 2, None, None, 8, None]})
        assert out["filled"] == [2.0, 2.0, 4.0, 6.0, 8.0, 8.0]

    def test_canonical_json_is_key_order_independent(self):
        a = self._run("stoicheion", "json.canonicalise@v1", {"value": {"b": 1, "a": 2}})
        b = self._run("stoicheion", "json.canonicalise@v1", {"value": {"a": 2, "b": 1}})
        assert a["sha256"] == b["sha256"]

    def test_a_diff_names_the_path_that_changed(self):
        out = self._run("stoicheion", "json.diff@v1",
                        {"a": {"user": {"age": 30}}, "b": {"user": {"age": 31}}})
        assert out["changed"] == [{"path": "/user/age", "from": 30, "to": 31}]
        assert out["identical"] is False

    def test_deterministic_ids_agree_across_calls_and_differ_by_name(self):
        one = self._run("stoicheion", "id.deterministic@v1", {"name": "order-1"})
        same = self._run("stoicheion", "id.deterministic@v1", {"name": "order-1"})
        other = self._run("stoicheion", "id.deterministic@v1", {"name": "order-2"})
        assert one["uuid"] == same["uuid"] != other["uuid"]

    def test_a_geohash_round_trips_to_within_its_cell(self):
        point = {"lat": 51.5074, "lon": -0.1278}
        code = self._run("horizon", "geo.geohash-encode@v1",
                         {"point": point, "precision": 9})["geohash"]
        back = self._run("horizon", "geo.geohash-decode@v1", {"geohash": code})
        assert abs(back["lat"] - point["lat"]) < 0.001
        assert abs(back["lon"] - point["lon"]) < 0.001

    def test_the_centroid_survives_the_antimeridian(self):
        """Averaging the numbers would put this point in the middle of Africa."""
        out = self._run("horizon", "geo.centroid@v1",
                        {"points": [{"lat": 0, "lon": 179}, {"lat": 0, "lon": -179}]})
        assert abs(abs(out["lon"]) - 180) < 0.001

    def test_dew_point_is_below_the_air_temperature(self):
        out = self._run("horizon", "sensor.dewpoint@v1",
                        {"temperature_c": 22.5, "relative_humidity_pct": 61})
        assert 14.0 < out["dew_point_c"] < 15.5

    def test_saturated_air_has_the_dew_point_at_the_temperature(self):
        out = self._run("horizon", "sensor.dewpoint@v1",
                        {"temperature_c": 20, "relative_humidity_pct": 100})
        assert out["dew_point_c"] == pytest.approx(20, abs=0.05)

    def test_hysteresis_turns_a_flapping_sensor_into_one_alert(self):
        out = self._run("horizon", "sensor.threshold-alerts@v1",
                        {"series": [0, 9, 4, 9, 4, 9, 0], "high": 5, "clear": 1})
        assert out["count"] == 1, "each dip below the high mark raised a new alert"

    def test_debounce_ignores_a_single_stray_sample(self):
        out = self._run("horizon", "sensor.debounce@v1",
                        {"states": ["off", "off", "on", "off", "off"], "hold": 2})
        assert set(out["debounced"]) == {"off"}
        assert out["transitions"] == []

    def test_simplify_drops_a_point_that_is_on_the_line(self):
        out = self._run("horizon", "geo.simplify@v1", {
            "points": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.5}, {"lat": 0, "lon": 1}],
            "tolerance_m": 1,
        })
        assert out["to_points"] == 2
