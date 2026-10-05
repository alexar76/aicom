"""Is that difference real? A/B tests, confidence intervals, sample sizes — computed, not
eyeballed, with the assumptions each answer rests on stated next to it.

  proportions   two conversion rates: pooled z test, the difference's CI, Wilson CIs per arm,
                and Fisher's exact test whenever an expected count is below 5
  means         Welch's t test from summaries (mean, sd, n) or raw values; Cohen's d
  chi_square    an r x c table of counts: Pearson's chi-square, expected counts, Cramer's V
  sample_size   per group, for a proportion (baseline + minimum detectable effect) or a mean
  proportion_ci one rate: Wilson and Clopper-Pearson (exact) intervals
  describe      a sample: mean, median, sd, quartiles, Tukey outliers

The t, chi-square and beta distributions are computed here (regularized incomplete beta and
gamma functions, Lentz continued fractions); the normal one is the standard library's.
A p-value answers "how surprising if there were no difference", not "how likely it is real".
"""

import math
import statistics

NORMAL = statistics.NormalDist()
MAX_VALUES = 100000
MAX_CELLS = 400

# ------------------------------------------------------------------ special functions


def _betacf(a, b, x):
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def gammainc_upper(s, x):
    """Regularized upper incomplete gamma Q(s, x)."""
    if x <= 0.0:
        return 1.0
    if x < s + 1.0:
        term = total = 1.0 / s
        k = s
        for _ in range(10000):
            k += 1.0
            term *= x / k
            total += term
            if abs(term) < abs(total) * 1e-16:
                break
        return 1.0 - total * math.exp(-x + s * math.log(x) - math.lgamma(s))
    tiny = 1e-300
    b = x + 1.0 - s
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return math.exp(-x + s * math.log(x) - math.lgamma(s)) * h


def t_two_sided_p(t, df):
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def t_cdf(t, df):
    tail = 0.5 * t_two_sided_p(t, df)
    return 1.0 - tail if t > 0 else tail


def t_quantile(p, df):
    """Inverse of t_cdf by bisection (monotone, so exact to the float)."""
    low, high = -1e6, 1e6
    for _ in range(200):
        mid = (low + high) / 2.0
        if t_cdf(mid, df) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def chi2_sf(x, df):
    return gammainc_upper(df / 2.0, x / 2.0)


def _beta_quantile(p, a, b):
    low, high = 0.0, 1.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if betainc(a, b, mid) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


# ------------------------------------------------------------------ inputs


def _count(value, where, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(where + " must be an integer >= " + str(minimum))
    return value


def _number(value, where, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(where + " must be a finite number")
    if (low is not None and value <= low) or (high is not None and value >= high):
        raise ValueError(where + " must be between " + str(low) + " and " + str(high))
    return float(value)


def _alpha(payload):
    return _number(payload.get("alpha", 0.05), "alpha", 0.0, 0.5)


def _alternative(payload):
    alt = payload.get("alternative", "two-sided")
    if alt not in ("two-sided", "greater", "less"):
        raise ValueError("alternative must be two-sided, greater (b > a) or less (b < a)")
    return alt


def _p_from_z(z, alt):
    if alt == "two-sided":
        return 2.0 * (1.0 - NORMAL.cdf(abs(z)))
    return 1.0 - NORMAL.cdf(z) if alt == "greater" else NORMAL.cdf(z)


def _r(value, digits=6):
    """Rounded to significant digits, so the answer does not pretend to 17 of them."""
    if not math.isfinite(value):
        return None
    return float(format(value, ".4g")) if digits == 4 else float(format(value, ".6g"))


def _wilson(k, n, alpha):
    z = NORMAL.inv_cdf(1.0 - alpha / 2.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [_r(max(0.0, centre - half)), _r(min(1.0, centre + half))]


def _fisher(a, b, c, d, alt):
    """Fisher's exact test on [[a, b], [c, d]] (rows: arm A, arm B; columns: success, fail)."""
    row1, col1, n = a + b, a + c, a + b + c + d
    low, high = max(0, col1 - (n - row1)), min(row1, col1)
    if high - low > 200000:
        return None

    def logp(x):
        return (math.lgamma(row1 + 1) - math.lgamma(x + 1) - math.lgamma(row1 - x + 1)
                + math.lgamma(n - row1 + 1) - math.lgamma(col1 - x + 1)
                - math.lgamma(n - row1 - col1 + x + 1) - math.lgamma(n + 1)
                + math.lgamma(col1 + 1) + math.lgamma(n - col1 + 1))

    observed = logp(a)
    total = 0.0
    for x in range(low, high + 1):
        lp = logp(x)
        if alt == "two-sided":
            keep = lp <= observed + 1e-7
        elif alt == "greater":  # b's rate above a's: fewer successes in arm A
            keep = x <= a
        else:
            keep = x >= a
        if keep:
            total += math.exp(lp)
    return min(1.0, total)


# ------------------------------------------------------------------ operations


def _proportions(payload):
    alpha, alt = _alpha(payload), _alternative(payload)
    arms = []
    for name in ("a", "b"):
        arm = payload.get(name)
        if not isinstance(arm, dict):
            raise ValueError("send '" + name + "': {successes, trials}")
        n = _count(arm.get("trials"), name + ".trials", 1)
        k = _count(arm.get("successes"), name + ".successes")
        if k > n:
            raise ValueError(name + ".successes is more than its trials")
        arms.append((k, n))
    (ka, na), (kb, nb) = arms
    pa, pb = ka / na, kb / nb
    pooled = (ka + kb) / (na + nb)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / na + 1 / nb))
    z = (pb - pa) / se_pooled if se_pooled > 0 else 0.0
    p_value = _p_from_z(z, alt) if se_pooled > 0 else 1.0
    se = math.sqrt(pa * (1 - pa) / na + pb * (1 - pb) / nb)
    zc = NORMAL.inv_cdf(1.0 - alpha / 2.0)
    expected = [pooled * na, (1 - pooled) * na, pooled * nb, (1 - pooled) * nb]
    out = {
        "op": "proportions", "rate_a": _r(pa), "rate_b": _r(pb), "difference": _r(pb - pa),
        "relative_lift": _r((pb - pa) / pa) if pa > 0 else None,
        "test": "two-proportion z test (pooled)", "z": _r(z), "p_value": _r(p_value),
        "alternative": alt, "alpha": alpha, "significant": p_value < alpha,
        "ci_difference": [_r(pb - pa - zc * se), _r(pb - pa + zc * se)],
        "ci_a": _wilson(ka, na, alpha), "ci_b": _wilson(kb, nb, alpha),
        "assumptions": ["independent visitors, each counted once, in one arm",
                        "the sample size was fixed before looking (no peeking)"],
    }
    if min(expected) < 5:
        fisher = _fisher(ka, na - ka, kb, nb - kb, alt)
        out["small_counts"] = "an expected count is below 5: prefer Fisher's exact test"
        if fisher is not None:
            out["fisher_p_value"] = _r(fisher)
            out["significant"] = fisher < alpha
            out["test"] = "Fisher's exact test (small counts)"
    return out


def _summary(arm, name):
    if not isinstance(arm, dict):
        raise ValueError("send '" + name + "': {mean, sd, n} or {values}")
    if "values" in arm:
        values = arm.get("values")
        if not isinstance(values, list) or len(values) < 2 or len(values) > MAX_VALUES:
            raise ValueError(name + ".values needs 2 to " + str(MAX_VALUES) + " numbers")
        data = [_number(v, name + ".values") for v in values]
        return statistics.fmean(data), statistics.stdev(data), len(data)
    return (_number(arm.get("mean"), name + ".mean"),
            _number(arm.get("sd"), name + ".sd", 0.0, None) if arm.get("sd") != 0 else 0.0,
            _count(arm.get("n"), name + ".n", 2))


def _means(payload):
    alpha, alt = _alpha(payload), _alternative(payload)
    ma, sa, na = _summary(payload.get("a"), "a")
    mb, sb, nb = _summary(payload.get("b"), "b")
    va, vb = sa * sa / na, sb * sb / nb
    se = math.sqrt(va + vb)
    if se == 0:
        raise ValueError("both samples have zero spread: there is nothing to test")
    df = (va + vb) ** 2 / ((va * va) / (na - 1) + (vb * vb) / (nb - 1))
    t = (mb - ma) / se
    if alt == "two-sided":
        p_value = t_two_sided_p(t, df)
    else:
        p_value = 1.0 - t_cdf(t, df) if alt == "greater" else t_cdf(t, df)
    tc = t_quantile(1.0 - alpha / 2.0, df)
    pooled_sd = math.sqrt(((na - 1) * sa * sa + (nb - 1) * sb * sb) / (na + nb - 2))
    return {"op": "means", "mean_a": _r(ma), "mean_b": _r(mb), "difference": _r(mb - ma),
            "test": "Welch's t test", "t": _r(t), "df": _r(df), "p_value": _r(p_value),
            "alternative": alt, "alpha": alpha, "significant": p_value < alpha,
            "ci_difference": [_r(mb - ma - tc * se), _r(mb - ma + tc * se)],
            "cohens_d": _r((mb - ma) / pooled_sd) if pooled_sd > 0 else None,
            "assumptions": ["independent samples", "roughly normal means (large n or "
                            "near-normal data); unequal variances are fine"]}


def _chi_square(payload):
    table = payload.get("table")
    if not isinstance(table, list) or len(table) < 2 or not all(
            isinstance(r, list) and len(r) == len(table[0]) for r in table) or len(table[0]) < 2:
        raise ValueError("table must be at least 2 x 2: a list of equal-length rows of counts")
    if len(table) * len(table[0]) > MAX_CELLS:
        raise ValueError("at most " + str(MAX_CELLS) + " cells")
    counts = [[_count(v, "table cell") for v in row] for row in table]
    rows = [sum(r) for r in counts]
    cols = [sum(c) for c in zip(*counts, strict=True)]
    n = sum(rows)
    if n == 0 or 0 in rows or 0 in cols:
        raise ValueError("every row and column needs at least one count")
    expected = [[rows[i] * cols[j] / n for j in range(len(cols))] for i in range(len(rows))]
    chi2 = sum((counts[i][j] - expected[i][j]) ** 2 / expected[i][j]
               for i in range(len(rows)) for j in range(len(cols)))
    df = (len(rows) - 1) * (len(cols) - 1)
    p_value = chi2_sf(chi2, df)
    alpha = _alpha(payload)
    out = {"op": "chi_square", "chi2": _r(chi2), "df": df, "p_value": _r(p_value),
           "alpha": alpha, "significant": p_value < alpha,
           "cramers_v": _r(math.sqrt(chi2 / (n * (min(len(rows), len(cols)) - 1)))),
           "expected": [[_r(e, 4) for e in row] for row in expected]}
    low = sum(1 for row in expected for e in row if e < 5)
    if low:
        out["small_counts"] = str(low) + " expected counts are below 5: the chi-square " \
                                         "approximation is unreliable"
    return out


def _sample_size(payload):
    alpha = _alpha(payload)
    power = _number(payload.get("power", 0.8), "power", 0.0, 1.0)
    alt = _alternative(payload)
    z_alpha = NORMAL.inv_cdf(1.0 - (alpha / 2.0 if alt == "two-sided" else alpha))
    z_beta = NORMAL.inv_cdf(power)
    metric = payload.get("metric", "proportion")
    if metric == "proportion":
        p1 = _number(payload.get("baseline"), "baseline", 0.0, 1.0)
        if "mde" in payload:
            p2 = p1 + _number(payload.get("mde"), "mde")
        else:
            p2 = p1 * (1 + _number(payload.get("relative_mde"), "relative_mde"))
        if not 0 < p2 < 1 or p2 == p1:
            raise ValueError("baseline plus the effect must be a different rate between 0 and 1")
        mean_p = (p1 + p2) / 2
        n = ((z_alpha * math.sqrt(2 * mean_p * (1 - mean_p))
              + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2) / (p2 - p1) ** 2
        detail = {"baseline": p1, "target": _r(p2)}
    elif metric == "mean":
        sd = _number(payload.get("sd"), "sd", 0.0, None)
        delta = _number(payload.get("mde"), "mde")
        if delta == 0:
            raise ValueError("mde must not be zero")
        n = 2 * ((z_alpha + z_beta) * sd / delta) ** 2
        detail = {"sd": sd, "mde": delta}
    else:
        raise ValueError("metric must be proportion or mean")
    per_group = math.ceil(n)
    return dict({"op": "sample_size", "metric": metric, "per_group": per_group,
                 "total": 2 * per_group, "alpha": alpha, "power": power, "alternative": alt,
                 "method": "normal approximation"}, **detail)


def _proportion_ci(payload):
    n = _count(payload.get("trials"), "trials", 1)
    k = _count(payload.get("successes"), "successes")
    if k > n:
        raise ValueError("successes is more than trials")
    alpha = _alpha(payload)
    lower = 0.0 if k == 0 else _beta_quantile(alpha / 2.0, k, n - k + 1)
    upper = 1.0 if k == n else _beta_quantile(1.0 - alpha / 2.0, k + 1, n - k)
    return {"op": "proportion_ci", "rate": _r(k / n), "confidence": 1 - alpha,
            "wilson": _wilson(k, n, alpha), "clopper_pearson": [_r(lower), _r(upper)]}


def _describe(payload):
    values = payload.get("values")
    if not isinstance(values, list) or len(values) < 2 or len(values) > MAX_VALUES:
        raise ValueError("values needs 2 to " + str(MAX_VALUES) + " numbers")
    data = sorted(_number(v, "values") for v in values)
    q1, q2, q3 = statistics.quantiles(data, n=4, method="inclusive")
    iqr = q3 - q1
    outliers = [v for v in data if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr]
    return {"op": "describe", "n": len(data), "mean": _r(statistics.fmean(data)),
            "median": _r(q2), "sd": _r(statistics.stdev(data)), "min": _r(data[0]),
            "max": _r(data[-1]), "q1": _r(q1), "q3": _r(q3), "iqr": _r(iqr),
            "outliers": [_r(v) for v in outliers[:100]], "outlier_count": len(outliers),
            "outlier_rule": "Tukey: below q1 - 1.5 IQR or above q3 + 1.5 IQR"}


OPS = {"proportions": _proportions, "means": _means, "chi_square": _chi_square,
       "sample_size": _sample_size, "proportion_ci": _proportion_ci, "describe": _describe}


def handle(payload):
    op = payload.get("op")
    if op not in OPS:
        raise ValueError("op must be one of " + ", ".join(OPS))
    return OPS[op](payload)
