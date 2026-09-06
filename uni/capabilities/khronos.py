"""KHRONOS — time series and descriptive statistics.

The largest catalogue in the bubble, mirroring the shape of the live oracle family. Every
function is ordinary, checkable statistics: no model, no network, no lookup table. Where a
formula has more than one convention (sample vs population variance, quantile interpolation,
tie handling in a rank correlation) the choice is stated in the docstring, because a consumer
comparing two providers needs to know which one it asked for.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

from uni.capabilities import (
    SERIES_SCHEMA, Capability, Catalogue, InvalidInput, choice, integer, number, numbers,
    rounded,
)

OBJ = {"type": "object"}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _quantile(sorted_xs: list[float], q: float) -> float:
    """Linear interpolation between order statistics — the 'inclusive' convention, the same
    one numpy calls 'linear' and Excel calls PERCENTILE.INC."""
    if not sorted_xs:
        raise InvalidInput("cannot take a quantile of an empty series")
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = (len(sorted_xs) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_xs[int(pos)]
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def _ranks(xs: list[float]) -> list[float]:
    """Average ranks, so ties do not silently bias a rank correlation."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None  # a constant series has no linear relationship to report
    return num / (dx * dy)


# ── capabilities ─────────────────────────────────────────────────────────────────

def describe(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    s = sorted(xs)
    n = len(xs)
    mean = _mean(xs)
    out = {
        "n": n, "mean": rounded(mean), "median": rounded(_quantile(s, 0.5)),
        "min": rounded(s[0]), "max": rounded(s[-1]), "range": rounded(s[-1] - s[0]),
        "sum": rounded(sum(xs)),
        "p25": rounded(_quantile(s, 0.25)), "p75": rounded(_quantile(s, 0.75)),
        "iqr": rounded(_quantile(s, 0.75) - _quantile(s, 0.25)),
    }
    if n >= 2:
        var = statistics.variance(xs)  # sample variance, n-1
        out["variance"] = rounded(var)
        out["stdev"] = rounded(math.sqrt(var))
        out["cv"] = rounded(math.sqrt(var) / mean) if mean else None
    else:
        out["variance"] = out["stdev"] = out["cv"] = None
    if n >= 3 and out["stdev"]:
        sd = out["stdev"]
        out["skewness"] = rounded(sum(((x - mean) / sd) ** 3 for x in xs) * n / ((n - 1) * (n - 2)))
    else:
        out["skewness"] = None
    if n >= 4 and out["stdev"]:
        sd = out["stdev"]
        m4 = sum(((x - mean) / sd) ** 4 for x in xs)
        g2 = (n * (n + 1) * m4) / ((n - 1) * (n - 2) * (n - 3))
        g2 -= 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
        out["excess_kurtosis"] = rounded(g2)
    else:
        out["excess_kurtosis"] = None
    return out


def quantiles(p: dict[str, Any]) -> Any:
    xs = sorted(numbers(p, minimum=1))
    qs = p.get("quantiles", [0.05, 0.25, 0.5, 0.75, 0.95])
    if not isinstance(qs, list) or not qs:
        raise InvalidInput("quantiles must be a non-empty array")
    if len(qs) > 100:
        raise InvalidInput("quantiles is limited to 100 values")
    out = {}
    for q in qs:
        if isinstance(q, bool) or not isinstance(q, (int, float)) or not 0 <= q <= 1:
            raise InvalidInput(f"quantile {q!r} must be a number in [0, 1]")
        out[f"{float(q):g}"] = rounded(_quantile(xs, float(q)))
    return {"n": len(xs), "quantiles": out}


def ewma(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    alpha = number(p, "alpha", 0.3, minimum=0.0, maximum=1.0)
    if alpha == 0:
        raise InvalidInput("alpha must be greater than 0 — an alpha of 0 never updates")
    out, prev = [], xs[0]
    for x in xs:
        prev = alpha * x + (1 - alpha) * prev
        out.append(rounded(prev))
    return {"alpha": alpha, "smoothed": out, "last": out[-1]}


def sma(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    window = integer(p, "window", 3, minimum=1, maximum=len(xs))
    out = [rounded(_mean(xs[i - window + 1:i + 1])) for i in range(window - 1, len(xs))]
    return {"window": window, "moving_average": out, "n": len(out)}


def linear_regression(p: dict[str, Any]) -> Any:
    ys = numbers(p, "series", minimum=2)
    xs = numbers(p, "x", minimum=2) if isinstance(p.get("x"), list) else [float(i) for i in range(len(ys))]
    if len(xs) != len(ys):
        raise InvalidInput("x and series must be the same length")
    mx, my = _mean(xs), _mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise InvalidInput("x has no variance — a slope is undefined")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    fitted = [intercept + slope * x for x in xs]
    ss_res = sum((y - f) ** 2 for y, f in zip(ys, fitted))
    ss_tot = sum((y - my) ** 2 for y in ys)
    horizon = integer(p, "forecast", 0, minimum=0, maximum=1000)
    step = (xs[-1] - xs[-2]) if len(xs) >= 2 else 1.0
    return {
        "slope": rounded(slope), "intercept": rounded(intercept),
        "r_squared": rounded(1 - ss_res / ss_tot) if ss_tot else None,
        "residual_stdev": rounded(math.sqrt(ss_res / (len(ys) - 2))) if len(ys) > 2 else None,
        "forecast": [rounded(intercept + slope * (xs[-1] + step * (h + 1))) for h in range(horizon)],
    }


def holt_forecast(p: dict[str, Any]) -> Any:
    """Holt's linear trend method — level and trend, no seasonality."""
    xs = numbers(p, minimum=2)
    alpha = number(p, "alpha", 0.5, minimum=0.01, maximum=1.0)
    beta = number(p, "beta", 0.1, minimum=0.0, maximum=1.0)
    horizon = integer(p, "horizon", 3, minimum=1, maximum=1000)
    level, trend = xs[0], xs[1] - xs[0]
    fitted = []
    for x in xs[1:]:
        prev_level = level
        level = alpha * x + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        fitted.append(rounded(level))
    return {
        "level": rounded(level), "trend": rounded(trend),
        "fitted": fitted,
        "forecast": [rounded(level + (h + 1) * trend) for h in range(horizon)],
    }


def outliers_mad(p: dict[str, Any]) -> Any:
    """Median absolute deviation, scaled by 1.4826 so the threshold is in robust sigmas."""
    xs = numbers(p, minimum=1)
    threshold = number(p, "threshold", 3.5, minimum=0.1, maximum=100.0)
    med = _quantile(sorted(xs), 0.5)
    mad = _quantile(sorted(abs(x - med) for x in xs), 0.5) * 1.4826
    if mad == 0:
        return {"median": rounded(med), "mad": 0.0, "outliers": [],
                "note": "every deviation is zero — no scale to measure against"}
    flagged = [
        {"index": i, "value": rounded(x), "z": rounded((x - med) / mad)}
        for i, x in enumerate(xs) if abs(x - med) / mad > threshold
    ]
    return {"median": rounded(med), "mad": rounded(mad), "threshold": threshold,
            "outliers": flagged, "outlier_count": len(flagged)}


def outliers_iqr(p: dict[str, Any]) -> Any:
    """Tukey fences at k * IQR outside the quartiles."""
    xs = numbers(p, minimum=1)
    k = number(p, "k", 1.5, minimum=0.0, maximum=100.0)
    s = sorted(xs)
    q1, q3 = _quantile(s, 0.25), _quantile(s, 0.75)
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    flagged = [{"index": i, "value": rounded(x)} for i, x in enumerate(xs) if x < lo or x > hi]
    return {"q1": rounded(q1), "q3": rounded(q3), "iqr": rounded(iqr),
            "lower_fence": rounded(lo), "upper_fence": rounded(hi),
            "outliers": flagged, "outlier_count": len(flagged)}


def autocorrelation(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=2)
    max_lag = integer(p, "max_lag", min(10, len(xs) - 1), minimum=1, maximum=len(xs) - 1)
    mean = _mean(xs)
    denom = sum((x - mean) ** 2 for x in xs)
    if denom == 0:
        raise InvalidInput("series is constant — autocorrelation is undefined")
    acf = {}
    for lag in range(1, max_lag + 1):
        num = sum((xs[i] - mean) * (xs[i - lag] - mean) for i in range(lag, len(xs)))
        acf[str(lag)] = rounded(num / denom)
    # Two different questions, and conflating them is a real trap: the strongest DEPENDENCE
    # can be negative — an alternating series correlates -0.875 at lag 1 and +0.75 at lag 2 —
    # while a caller looking for a PERIOD wants the strongest positive lag. Report both.
    strongest = max(acf, key=lambda k: abs(acf[k]))
    positive = [k for k in acf if acf[k] > 0]
    period = max(positive, key=lambda k: acf[k]) if positive else None
    return {
        "acf": acf,
        "strongest_lag": int(strongest),
        "strongest_value": acf[strongest],
        "strongest_positive_lag": int(period) if period else None,
        "strongest_positive_value": acf[period] if period else None,
        "note": "strongest_lag is by magnitude and may be negative; "
                "strongest_positive_lag is the period candidate",
    }


def changepoint_cusum(p: dict[str, Any]) -> Any:
    """Two-sided CUSUM over the standardised series. Reports where the cumulative deviation
    first exceeds the threshold in either direction."""
    xs = numbers(p, minimum=3)
    threshold = number(p, "threshold", 5.0, minimum=0.1, maximum=1000.0)
    drift = number(p, "drift", 0.5, minimum=0.0, maximum=100.0)
    mean = _mean(xs)
    sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
    if sd == 0:
        return {"changepoints": [], "note": "series is constant"}
    pos = neg = 0.0
    points = []
    for i, x in enumerate(xs):
        z = (x - mean) / sd
        pos = max(0.0, pos + z - drift)
        neg = min(0.0, neg + z + drift)
        if pos > threshold:
            points.append({"index": i, "direction": "up", "statistic": rounded(pos)})
            pos = 0.0
        elif -neg > threshold:
            points.append({"index": i, "direction": "down", "statistic": rounded(-neg)})
            neg = 0.0
    return {"changepoints": points, "count": len(points), "threshold": threshold}


def seasonal_strength(p: dict[str, Any]) -> Any:
    """Naive additive decomposition: a centred moving average as the trend, per-phase means
    as the season, and the variance ratio of the remainder as the strength."""
    xs = numbers(p, minimum=4)
    period = integer(p, "period", minimum=2, maximum=max(2, len(xs) // 2))
    if len(xs) < 2 * period:
        raise InvalidInput(f"series needs at least {2 * period} points for period {period}")
    trend = []
    half = period // 2
    for i in range(len(xs)):
        lo, hi = max(0, i - half), min(len(xs), i + half + 1)
        trend.append(_mean(xs[lo:hi]))
    detrended = [x - t for x, t in zip(xs, trend)]
    season = []
    for phase in range(period):
        vals = detrended[phase::period]
        season.append(_mean(vals) if vals else 0.0)
    centre = _mean(season)
    season = [s - centre for s in season]
    remainder = [d - season[i % period] for i, d in enumerate(detrended)]
    var_r = statistics.pvariance(remainder)
    var_sr = statistics.pvariance([s + r for s, r in zip(
        (season[i % period] for i in range(len(xs))), remainder)])
    strength = 0.0 if var_sr == 0 else max(0.0, 1 - var_r / var_sr)
    return {"period": period, "seasonal_profile": [rounded(s) for s in season],
            "strength": rounded(strength),
            "interpretation": "strong" if strength > 0.6 else "weak" if strength < 0.3 else "moderate"}


def resample(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    factor = integer(p, "factor", 2, minimum=1, maximum=len(xs))
    how = choice(p, "how", ("mean", "sum", "min", "max", "median", "last"), "mean")
    fns = {"mean": _mean, "sum": sum, "min": min, "max": max,
           "median": lambda b: _quantile(sorted(b), 0.5), "last": lambda b: b[-1]}
    buckets = [xs[i:i + factor] for i in range(0, len(xs), factor)]
    return {"factor": factor, "how": how, "n": len(buckets),
            "resampled": [rounded(fns[how](b)) for b in buckets]}


def difference(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=2)
    order = integer(p, "order", 1, minimum=1, maximum=10)
    if order >= len(xs):
        raise InvalidInput(f"order {order} needs a series longer than {order}")
    cur = xs
    for _ in range(order):
        cur = [b - a for a, b in zip(cur, cur[1:])]
    return {"order": order, "differenced": [rounded(v) for v in cur], "n": len(cur)}


def normalise(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    method = choice(p, "method", ("zscore", "minmax", "robust"), "zscore")
    if method == "zscore":
        mean = _mean(xs)
        sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
        if sd == 0:
            raise InvalidInput("series has no spread — a z-score is undefined")
        out = [(x - mean) / sd for x in xs]
    elif method == "minmax":
        lo, hi = min(xs), max(xs)
        if hi == lo:
            raise InvalidInput("series has no range — min-max scaling is undefined")
        out = [(x - lo) / (hi - lo) for x in xs]
    else:
        s = sorted(xs)
        med = _quantile(s, 0.5)
        iqr = _quantile(s, 0.75) - _quantile(s, 0.25)
        if iqr == 0:
            raise InvalidInput("interquartile range is zero — robust scaling is undefined")
        out = [(x - med) / iqr for x in xs]
    return {"method": method, "normalised": [rounded(v) for v in out]}


def correlation(p: dict[str, Any]) -> Any:
    xs = numbers(p, "a", minimum=2)
    ys = numbers(p, "b", minimum=2)
    if len(xs) != len(ys):
        raise InvalidInput("a and b must be the same length")
    pearson = _pearson(xs, ys)
    spearman = _pearson(_ranks(xs), _ranks(ys))
    return {
        "n": len(xs),
        "pearson": rounded(pearson) if pearson is not None else None,
        "spearman": rounded(spearman) if spearman is not None else None,
        "note": None if pearson is not None else "one series is constant",
    }


def entropy(p: dict[str, Any]) -> Any:
    """Shannon entropy of the empirical distribution over equal-width bins, in bits."""
    xs = numbers(p, minimum=1)
    bins = integer(p, "bins", 10, minimum=2, maximum=1000)
    lo, hi = min(xs), max(xs)
    if hi == lo:
        return {"entropy_bits": 0.0, "max_entropy_bits": rounded(math.log2(bins)),
                "normalised": 0.0, "note": "series is constant"}
    counts = [0] * bins
    for x in xs:
        idx = min(bins - 1, int((x - lo) / (hi - lo) * bins))
        counts[idx] += 1
    total = len(xs)
    h = -sum((c / total) * math.log2(c / total) for c in counts if c)
    return {"entropy_bits": rounded(h), "max_entropy_bits": rounded(math.log2(bins)),
            "normalised": rounded(h / math.log2(bins)), "bins": bins}


def histogram(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    bins = integer(p, "bins", 10, minimum=1, maximum=1000)
    lo, hi = min(xs), max(xs)
    if hi == lo:
        return {"bins": [{"lower": rounded(lo), "upper": rounded(hi), "count": len(xs)}],
                "note": "series is constant"}
    width = (hi - lo) / bins
    counts = [0] * bins
    for x in xs:
        counts[min(bins - 1, int((x - lo) / width))] += 1
    return {"bins": [
        {"lower": rounded(lo + i * width), "upper": rounded(lo + (i + 1) * width), "count": c}
        for i, c in enumerate(counts)
    ]}


def cumulative(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    total, running = 0.0, []
    for x in xs:
        total += x
        running.append(total)
    peak, drawdowns = xs[0], []
    for x in xs:
        peak = max(peak, x)
        drawdowns.append(x - peak)
    return {
        "cumulative_sum": [rounded(v) for v in running],
        "running_max": [rounded(v) for v in _running(xs, max)],
        "running_min": [rounded(v) for v in _running(xs, min)],
        "drawdown": [rounded(v) for v in drawdowns],
        "max_drawdown": rounded(min(drawdowns)),
    }


def _running(xs: list[float], fn) -> list[float]:
    out, cur = [], xs[0]
    for x in xs:
        cur = fn(cur, x)
        out.append(cur)
    return out


def stationarity(p: dict[str, Any]) -> Any:
    """A cheap, honest stationarity screen: split the series in half and compare mean and
    variance. Not a unit-root test, and it says so — a hint, not a verdict."""
    xs = numbers(p, minimum=4)
    half = len(xs) // 2
    a, b = xs[:half], xs[half:]
    mean_a, mean_b = _mean(a), _mean(b)
    var_a = statistics.pvariance(a)
    var_b = statistics.pvariance(b)
    pooled_sd = math.sqrt((var_a + var_b) / 2)
    mean_shift = abs(mean_b - mean_a) / pooled_sd if pooled_sd else 0.0
    var_ratio = (max(var_a, var_b) / min(var_a, var_b)) if min(var_a, var_b) > 0 else None
    likely = mean_shift < 0.5 and (var_ratio is None or var_ratio < 2.0)
    return {
        "first_half_mean": rounded(mean_a), "second_half_mean": rounded(mean_b),
        "mean_shift_sigmas": rounded(mean_shift),
        "variance_ratio": rounded(var_ratio) if var_ratio else None,
        "likely_stationary": likely,
        "method": "split-half moment comparison — a screen, not a unit-root test",
    }


def interpolate_gaps(p: dict[str, Any]) -> Any:
    """Linear fill of nulls. Leading and trailing gaps are held flat rather than
    extrapolated: inventing a trend beyond the data is how a gap becomes a claim."""
    raw = p.get("series")
    if not isinstance(raw, list) or not raw:
        raise InvalidInput("series must be a non-empty array of numbers or nulls")
    if len(raw) > 100_000:
        raise InvalidInput("series is limited to 100000 values")
    vals: list[float | None] = []
    for i, v in enumerate(raw):
        if v is None:
            vals.append(None)
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            raise InvalidInput(f"series[{i}] must be a number or null")
        else:
            vals.append(float(v))
    known = [i for i, v in enumerate(vals) if v is not None]
    if not known:
        raise InvalidInput("series has no known values to interpolate between")
    filled = list(vals)
    for i in range(len(filled)):
        if filled[i] is not None:
            continue
        before = [k for k in known if k < i]
        after = [k for k in known if k > i]
        if before and after:
            lo, hi = before[-1], after[0]
            span = hi - lo
            filled[i] = vals[lo] + (vals[hi] - vals[lo]) * (i - lo) / span
        else:
            filled[i] = vals[known[0]] if not before else vals[known[-1]]
    return {"filled": [rounded(v) for v in filled], "gaps_filled": len(vals) - len(known)}


CATALOGUE = Catalogue(
    product_id="khronos",
    name="KHRONOS Time Series",
    description="Descriptive statistics, smoothing, decomposition and forecasting over ordered numeric series",
    capabilities=[
        Capability("series.describe@v1", "Full descriptive statistics for a numeric series: moments, quartiles, spread and shape",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA}},
                   OBJ, 0.002, 40, describe, {"series": [3, 1, 4, 1, 5, 9, 2, 6]}),
        Capability("series.quantiles@v1", "Quantiles at arbitrary probabilities, linearly interpolated between order statistics",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "quantiles": {"type": "array", "items": {"type": "number"}}}},
                   OBJ, 0.002, 35, quantiles, {"series": [1, 2, 3, 4, 5], "quantiles": [0.1, 0.5, 0.9]}),
        Capability("series.ewma@v1", "Exponentially weighted moving average with a configurable smoothing factor",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "alpha": {"type": "number", "minimum": 0, "maximum": 1}}},
                   OBJ, 0.002, 35, ewma, {"series": [10, 12, 11, 15, 14], "alpha": 0.4}),
        Capability("series.moving-average@v1", "Simple moving average over a sliding window",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "window": {"type": "integer", "minimum": 1}}},
                   OBJ, 0.002, 35, sma, {"series": [1, 2, 3, 4, 5, 6], "window": 3}),
        Capability("series.linear-regression@v1", "Ordinary least squares fit with r-squared, residual spread and optional forecast",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "x": SERIES_SCHEMA, "forecast": {"type": "integer", "minimum": 0}}},
                   OBJ, 0.004, 60, linear_regression, {"series": [2, 4, 6.1, 7.9, 10], "forecast": 2}),
        Capability("series.holt-forecast@v1", "Holt linear-trend exponential smoothing with an h-step forecast",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "alpha": {"type": "number"}, "beta": {"type": "number"}, "horizon": {"type": "integer"}}},
                   OBJ, 0.006, 80, holt_forecast, {"series": [10, 11, 13, 14, 16, 17], "horizon": 3}),
        Capability("series.outliers-mad@v1", "Robust outlier detection by median absolute deviation, scaled to sigmas",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "threshold": {"type": "number"}}},
                   OBJ, 0.004, 45, outliers_mad, {"series": [1, 2, 1, 2, 40, 1, 2]}),
        Capability("series.outliers-iqr@v1", "Outlier detection by Tukey fences at k interquartile ranges",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "k": {"type": "number"}}},
                   OBJ, 0.003, 45, outliers_iqr, {"series": [1, 2, 3, 4, 5, 100]}),
        Capability("series.autocorrelation@v1", "Autocorrelation function up to a chosen lag, with the strongest lag identified",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "max_lag": {"type": "integer", "minimum": 1}}},
                   OBJ, 0.005, 70, autocorrelation, {"series": [1, 2, 1, 2, 1, 2, 1, 2], "max_lag": 4}),
        Capability("series.changepoint-cusum@v1", "Two-sided CUSUM changepoint detection over the standardised series",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "threshold": {"type": "number"}, "drift": {"type": "number"}}},
                   OBJ, 0.008, 90, changepoint_cusum, {"series": [1, 1, 1, 1, 9, 9, 9, 9]}),
        Capability("series.seasonal-strength@v1", "Additive decomposition into trend, season and remainder, with a strength score",
                   {"type": "object", "required": ["series", "period"], "properties": {"series": SERIES_SCHEMA, "period": {"type": "integer", "minimum": 2}}},
                   OBJ, 0.010, 120, seasonal_strength, {"series": [1, 5, 2, 6, 1, 5, 2, 6], "period": 4}),
        Capability("series.resample@v1", "Downsample into fixed-size buckets with a chosen aggregation",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "factor": {"type": "integer"}, "how": {"enum": ["mean", "sum", "min", "max", "median", "last"]}}},
                   OBJ, 0.002, 30, resample, {"series": [1, 2, 3, 4, 5, 6], "factor": 2, "how": "mean"}),
        Capability("series.difference@v1", "N-th order differencing, the usual first step toward stationarity",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "order": {"type": "integer", "minimum": 1}}},
                   OBJ, 0.002, 30, difference, {"series": [1, 4, 9, 16, 25], "order": 2}),
        Capability("series.normalise@v1", "Rescale by z-score, min-max or robust (median/IQR) normalisation",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "method": {"enum": ["zscore", "minmax", "robust"]}}},
                   OBJ, 0.002, 30, normalise, {"series": [10, 20, 30, 40], "method": "zscore"}),
        Capability("series.correlation@v1", "Pearson and Spearman correlation between two aligned series, ties averaged",
                   {"type": "object", "required": ["a", "b"], "properties": {"a": SERIES_SCHEMA, "b": SERIES_SCHEMA}},
                   OBJ, 0.004, 50, correlation, {"a": [1, 2, 3, 4], "b": [2, 4.1, 5.9, 8]}),
        Capability("series.entropy@v1", "Shannon entropy of the binned distribution, in bits, with the normalised value",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "bins": {"type": "integer", "minimum": 2}}},
                   OBJ, 0.003, 45, entropy, {"series": [1, 1, 2, 3, 5, 8, 13], "bins": 4}),
        Capability("series.histogram@v1", "Equal-width binned counts with explicit bin edges",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "bins": {"type": "integer", "minimum": 1}}},
                   OBJ, 0.002, 30, histogram, {"series": [1, 2, 2, 3, 3, 3, 4], "bins": 4}),
        Capability("series.cumulative@v1", "Cumulative sum, running extremes, drawdown curve and maximum drawdown",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA}},
                   OBJ, 0.003, 35, cumulative, {"series": [5, 7, 3, 9, 4]}),
        Capability("series.stationarity@v1", "Split-half moment comparison as a stationarity screen, stated as a hint not a test",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA}},
                   OBJ, 0.005, 55, stationarity, {"series": [1, 2, 1, 2, 8, 9, 8, 9]}),
        Capability("series.interpolate-gaps@v1", "Linear interpolation across nulls, holding the ends flat rather than extrapolating",
                   {"type": "object", "required": ["series"], "properties": {"series": {"type": "array", "items": {"type": ["number", "null"]}}}},
                   OBJ, 0.003, 40, interpolate_gaps, {"series": [1, None, 3, None, None, 6]}),
    ],
)
