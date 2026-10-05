"""stats.test@v1 against printed tables, closed forms and textbook examples.

No scipy here, so the references are the ones every statistics table prints (t and chi-square
critical values), identities with closed forms (I_x(a,1) = x^a, chi-square with 1 df against
the normal, Clopper-Pearson at 0 and n successes), Fisher's tea-tasting table (34/70), and
the A/B sample size Evan Miller's calculator gives for 5% -> 6% (8 158 per group).
"""

from __future__ import annotations

import math
import random
import statistics

import pytest

from hestia_agents.manifests import handler_source

N = statistics.NormalDist()


@pytest.fixture(scope="module")
def ns():
    namespace: dict = {}
    exec(compile(handler_source("stats-test"), "stats-test", "exec"), namespace)  # noqa: S102
    return namespace


@pytest.fixture(scope="module")
def handle(ns):
    return ns["handle"]


@pytest.mark.parametrize(("df", "critical"), [(1, 12.70620474), (2, 4.30265273), (5, 2.57058184),
                                              (10, 2.22813885), (30, 2.04227246),
                                              (120, 1.97993040)])
def test_t_critical_values(ns, df, critical) -> None:
    assert ns["t_quantile"](0.975, df) == pytest.approx(critical, abs=1e-7)
    assert ns["t_two_sided_p"](critical, df) == pytest.approx(0.05, abs=1e-9)


@pytest.mark.parametrize(("df", "critical"), [(1, 3.841458821), (2, 5.991464547),
                                              (4, 9.487729037), (10, 18.30703805),
                                              (30, 43.77297183)])
def test_chi_square_critical_values(ns, df, critical) -> None:
    assert ns["chi2_sf"](critical, df) == pytest.approx(0.05, abs=1e-8)


def test_closed_forms(ns) -> None:
    for x in (0.001, 0.2, 0.5, 0.97):
        for k in (0.5, 1, 3, 11.5):
            assert ns["betainc"](k, 1, x) == pytest.approx(x ** k, rel=1e-12)
            assert ns["betainc"](1, k, x) == pytest.approx(1 - (1 - x) ** k, rel=1e-12)
    for x in (0.01, 1, 3.84, 25):
        assert ns["chi2_sf"](x, 1) == pytest.approx(2 * (1 - N.cdf(math.sqrt(x))), abs=1e-14)
        assert ns["chi2_sf"](x, 2) == pytest.approx(math.exp(-x / 2), rel=1e-12)


def test_large_df_t_is_normal(ns) -> None:
    assert ns["t_quantile"](0.975, 1e7) == pytest.approx(N.inv_cdf(0.975), abs=1e-6)


# ------------------------------------------------------------------ proportions


def test_ab_test_by_hand(handle) -> None:
    out = handle({"op": "proportions", "a": {"successes": 200, "trials": 1000},
                  "b": {"successes": 250, "trials": 1000}})
    pooled = 450 / 2000
    z = 0.05 / math.sqrt(pooled * (1 - pooled) * 2 / 1000)
    assert out["z"] == pytest.approx(z, rel=1e-5)
    assert out["p_value"] == pytest.approx(2 * (1 - N.cdf(z)), rel=1e-5)
    assert out["significant"] is True and out["relative_lift"] == 0.25
    assert out["ci_difference"][0] > 0 and out["test"] == "two-proportion z test (pooled)"


def test_tea_tasting_goes_exact(handle) -> None:
    out = handle({"op": "proportions", "a": {"successes": 3, "trials": 4},
                  "b": {"successes": 1, "trials": 4}})
    assert out["fisher_p_value"] == pytest.approx(34 / 70, abs=1e-6)
    assert out["test"].startswith("Fisher") and out["significant"] is False
    one_sided = handle({"op": "proportions", "alternative": "less",
                        "a": {"successes": 3, "trials": 4}, "b": {"successes": 1, "trials": 4}})
    assert one_sided["fisher_p_value"] == pytest.approx(17 / 70, abs=1e-6)


def test_one_sided_halves_the_two_sided(handle) -> None:
    base = {"op": "proportions", "a": {"successes": 120, "trials": 1000},
            "b": {"successes": 150, "trials": 1000}}
    two = handle(base)["p_value"]
    assert handle({**base, "alternative": "greater"})["p_value"] == pytest.approx(two / 2, rel=1e-4)
    assert handle({**base, "alternative": "less"})["p_value"] == pytest.approx(1 - two / 2,
                                                                              rel=1e-4)


# ------------------------------------------------------------------ means


def test_welch_by_hand_and_from_raw_values(handle) -> None:
    rng = random.Random(5)
    a = [rng.gauss(10, 2) for _ in range(40)]
    b = [rng.gauss(11, 3) for _ in range(25)]
    raw = handle({"op": "means", "a": {"values": a}, "b": {"values": b}})
    summary = handle({"op": "means",
                      "a": {"mean": statistics.fmean(a), "sd": statistics.stdev(a), "n": 40},
                      "b": {"mean": statistics.fmean(b), "sd": statistics.stdev(b), "n": 25}})
    assert raw == summary
    va, vb = statistics.variance(a) / 40, statistics.variance(b) / 25
    t = (statistics.fmean(b) - statistics.fmean(a)) / math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va * va / 39 + vb * vb / 24)
    assert raw["t"] == pytest.approx(t, rel=1e-5) and raw["df"] == pytest.approx(df, rel=1e-5)


def test_identical_samples_refused(handle) -> None:
    with pytest.raises(ValueError, match="zero spread"):
        handle({"op": "means", "a": {"values": [1, 1, 1]}, "b": {"values": [1, 1]}})


# ------------------------------------------------------------------ chi-square, sizes, CIs


def test_chi_square_two_by_two_matches_the_z_test(handle) -> None:
    chi = handle({"op": "chi_square", "table": [[200, 800], [250, 750]]})
    z = handle({"op": "proportions", "a": {"successes": 200, "trials": 1000},
                "b": {"successes": 250, "trials": 1000}})
    assert chi["chi2"] == pytest.approx(z["z"] ** 2, rel=1e-4)
    assert chi["p_value"] == pytest.approx(z["p_value"], rel=1e-4) and chi["df"] == 1


def test_chi_square_warns_on_small_counts(handle) -> None:
    out = handle({"op": "chi_square", "table": [[1, 2, 30], [4, 1, 40]]})
    assert out["df"] == 2 and "below 5" in out["small_counts"]


def test_sample_sizes(handle) -> None:
    assert handle({"op": "sample_size", "baseline": 0.05, "mde": 0.01})["per_group"] == 8158
    assert handle({"op": "sample_size", "baseline": 0.05,
                   "relative_mde": 0.2})["per_group"] == 8158
    assert handle({"op": "sample_size", "metric": "mean", "sd": 10, "mde": 5})["per_group"] == 63


def test_proportion_intervals_at_the_edges(handle) -> None:
    zero = handle({"op": "proportion_ci", "successes": 0, "trials": 10})
    assert zero["clopper_pearson"] == [0.0, pytest.approx(1 - 0.025 ** 0.1, rel=1e-5)]
    assert zero["wilson"][1] == pytest.approx(N.inv_cdf(0.975) ** 2 /
                                              (10 + N.inv_cdf(0.975) ** 2), rel=1e-5)
    full = handle({"op": "proportion_ci", "successes": 10, "trials": 10})
    assert full["clopper_pearson"] == [pytest.approx(0.025 ** 0.1, rel=1e-5), 1.0]


def test_describe(handle) -> None:
    out = handle({"op": "describe", "values": [1, 2, 3, 4, 5, 6, 7, 8, 9, 100]})
    assert out["median"] == 5.5 and out["outliers"] == [100.0] and out["n"] == 10


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"op": "anova"}, "op must be"),
        ({"op": "proportions", "a": {"successes": 5, "trials": 4}, "b": {"successes": 1,
                                                                          "trials": 4}}, "more"),
        ({"op": "proportions", "a": {"successes": 1, "trials": 0}, "b": {}}, "trials"),
        ({"op": "proportions", "a": {"successes": 1, "trials": 2}, "b": {"successes": 1,
                                                                          "trials": 2},
          "alpha": 0.7}, "alpha"),
        ({"op": "means", "a": {"values": [1]}, "b": {"values": [1, 2]}}, "2 to"),
        ({"op": "chi_square", "table": [[1, 2]]}, "2 x 2"),
        ({"op": "chi_square", "table": [[0, 0], [1, 2]]}, "every row"),
        ({"op": "sample_size", "baseline": 0.5, "mde": 0.6}, "between 0 and 1"),
        ({"op": "sample_size", "metric": "median"}, "metric"),
        ({"op": "describe", "values": [1, "x"]}, "finite number"),
    ],
)
def test_bad_requests_say_why(handle, payload, match) -> None:
    with pytest.raises(ValueError, match=match):
        handle(payload)
