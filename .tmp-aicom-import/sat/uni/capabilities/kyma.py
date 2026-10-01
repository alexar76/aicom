"""KYMA — signal processing over sampled waveforms.

A naive DFT rather than an FFT: the input sizes here are bounded to a few thousand samples,
and an O(n^2) transform that is obviously correct beats a hand-rolled radix-2 that is subtly
wrong on a non-power-of-two length. The bound is enforced, not assumed.
"""
from __future__ import annotations

import cmath
import math
import statistics
from typing import Any

from uni.capabilities import (
    SERIES_SCHEMA, Capability, Catalogue, InvalidInput, choice, integer, number, numbers,
    rounded,
)

OBJ = {"type": "object"}
MAX_DFT = 4096


def _dft(xs: list[float]) -> list[complex]:
    n = len(xs)
    if n > MAX_DFT:
        raise InvalidInput(f"a transform is limited to {MAX_DFT} samples, got {n}")
    return [
        sum(x * cmath.exp(-2j * math.pi * k * t / n) for t, x in enumerate(xs))
        for k in range(n // 2 + 1)
    ]


def spectrum(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=2, maximum=MAX_DFT)
    rate = number(p, "sample_rate_hz", 1.0, minimum=1e-9)
    mags = [abs(c) * 2 / len(xs) for c in _dft(xs)]
    mags[0] /= 2  # DC is not mirrored, so it must not be doubled
    return {
        "sample_rate_hz": rate, "n": len(xs),
        "bins": [
            {"frequency_hz": rounded(k * rate / len(xs)), "magnitude": rounded(m)}
            for k, m in enumerate(mags)
        ],
    }


def dominant_frequency(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=4, maximum=MAX_DFT)
    rate = number(p, "sample_rate_hz", 1.0, minimum=1e-9)
    mags = [abs(c) for c in _dft(xs)][1:]  # skip DC: a mean offset is not a frequency
    if not mags or max(mags) == 0:
        return {"dominant_frequency_hz": None, "note": "no periodic component above DC"}
    k = mags.index(max(mags)) + 1
    return {
        "dominant_frequency_hz": rounded(k * rate / len(xs)),
        "period_samples": rounded(len(xs) / k),
        "magnitude": rounded(max(mags) * 2 / len(xs)),
        "bin": k,
    }


def spectral_entropy(p: dict[str, Any]) -> Any:
    """Entropy of the normalised power spectrum — low means one tone, high means noise."""
    xs = numbers(p, minimum=4, maximum=MAX_DFT)
    power = [abs(c) ** 2 for c in _dft(xs)][1:]
    total = sum(power)
    if total == 0:
        return {"spectral_entropy_bits": 0.0, "normalised": 0.0, "note": "no energy above DC"}
    probs = [pw / total for pw in power if pw > 0]
    h = -sum(pr * math.log2(pr) for pr in probs)
    return {"spectral_entropy_bits": rounded(h),
            "max_bits": rounded(math.log2(len(power))),
            "normalised": rounded(h / math.log2(len(power))) if len(power) > 1 else 0.0,
            "interpretation": "tonal" if h < math.log2(len(power)) * 0.5 else "broadband"}


def band_energy(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=4, maximum=MAX_DFT)
    rate = number(p, "sample_rate_hz", 1.0, minimum=1e-9)
    bands = p.get("bands")
    if not isinstance(bands, list) or not bands:
        raise InvalidInput("bands must be a non-empty array of [low_hz, high_hz] pairs")
    if len(bands) > 64:
        raise InvalidInput("bands is limited to 64 entries")
    power = [abs(c) ** 2 for c in _dft(xs)]
    freqs = [k * rate / len(xs) for k in range(len(power))]
    total = sum(power) or 1.0
    out = []
    for band in bands:
        if (not isinstance(band, list) or len(band) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in band)):
            raise InvalidInput("each band must be a [low_hz, high_hz] pair of numbers")
        lo, hi = float(band[0]), float(band[1])
        if hi < lo:
            raise InvalidInput(f"band [{lo}, {hi}] has its bounds reversed")
        e = sum(pw for f, pw in zip(freqs, power) if lo <= f <= hi)
        out.append({"low_hz": lo, "high_hz": hi, "energy": rounded(e),
                    "share": rounded(e / total)})
    return {"bands": out, "total_energy": rounded(total)}


def rms(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=1)
    peak = max(abs(x) for x in xs)
    root = math.sqrt(sum(x * x for x in xs) / len(xs))
    return {
        "rms": rounded(root), "peak": rounded(peak),
        "crest_factor": rounded(peak / root) if root else None,
        "peak_to_peak": rounded(max(xs) - min(xs)),
        "mean": rounded(sum(xs) / len(xs)),
    }


def zero_crossing_rate(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=2)
    centre = choice(p, "reference", ("zero", "mean"), "zero")
    offset = (sum(xs) / len(xs)) if centre == "mean" else 0.0
    shifted = [x - offset for x in xs]
    crossings = sum(
        1 for a, b in zip(shifted, shifted[1:])
        if (a < 0 <= b) or (b < 0 <= a)
    )
    return {"crossings": crossings, "rate": rounded(crossings / (len(xs) - 1)),
            "reference": centre}


def convolve(p: dict[str, Any]) -> Any:
    xs = numbers(p, "signal", minimum=1, maximum=4096)
    k = numbers(p, "kernel", minimum=1, maximum=1024)
    mode = choice(p, "mode", ("full", "same", "valid"), "full")
    full = [
        sum(xs[i - j] * k[j] for j in range(len(k)) if 0 <= i - j < len(xs))
        for i in range(len(xs) + len(k) - 1)
    ]
    if mode == "same":
        start = (len(k) - 1) // 2
        out = full[start:start + len(xs)]
    elif mode == "valid":
        if len(k) > len(xs):
            raise InvalidInput("valid mode needs a kernel no longer than the signal")
        out = full[len(k) - 1:len(xs)]
    else:
        out = full
    return {"mode": mode, "convolved": [rounded(v) for v in out], "n": len(out)}


def cross_correlation_lag(p: dict[str, Any]) -> Any:
    """The lag at which b best matches a — the standard way to measure a delay between two
    recordings of the same event."""
    a = numbers(p, "a", minimum=2, maximum=4096)
    b = numbers(p, "b", minimum=2, maximum=4096)
    max_lag = integer(p, "max_lag", min(len(a), len(b)) - 1, minimum=1,
                      maximum=min(len(a), len(b)) - 1)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    da = [x - ma for x in a]
    db = [x - mb for x in b]
    norm = math.sqrt(sum(x * x for x in da) * sum(x * x for x in db))
    if norm == 0:
        raise InvalidInput("one of the series is constant — correlation is undefined")
    best_lag, best = 0, -2.0
    values = {}
    for lag in range(-max_lag, max_lag + 1):
        acc = 0.0
        for i in range(len(da)):
            j = i + lag
            if 0 <= j < len(db):
                acc += da[i] * db[j]
        r = acc / norm
        values[str(lag)] = rounded(r)
        if r > best:
            best, best_lag = r, lag
    return {"best_lag": best_lag, "best_correlation": rounded(best), "correlation": values}


def median_filter(p: dict[str, Any]) -> Any:
    """Impulse-noise removal that a moving average cannot do: a single wild sample moves a
    mean and does not move a median."""
    xs = numbers(p, minimum=1)
    window = integer(p, "window", 3, minimum=1, maximum=min(999, len(xs)))
    if window % 2 == 0:
        raise InvalidInput("window must be odd so the filter has a centre sample")
    half = window // 2
    out = []
    for i in range(len(xs)):
        lo, hi = max(0, i - half), min(len(xs), i + half + 1)
        out.append(statistics.median(xs[lo:hi]))
    return {"window": window, "filtered": [rounded(v) for v in out]}


def envelope(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=2)
    window = integer(p, "window", 5, minimum=1, maximum=min(999, len(xs)))
    upper, lower = [], []
    for i in range(len(xs)):
        lo, hi = max(0, i - window // 2), min(len(xs), i + window // 2 + 1)
        upper.append(max(xs[lo:hi]))
        lower.append(min(xs[lo:hi]))
    return {"upper": [rounded(v) for v in upper], "lower": [rounded(v) for v in lower],
            "width": [rounded(u - l) for u, l in zip(upper, lower)]}


def snr(p: dict[str, Any]) -> Any:
    """Signal-to-noise ratio in dB, taking the smoothed series as signal and the residual as
    noise. Stated that way because 'noise' is a modelling choice, not a measurement."""
    xs = numbers(p, minimum=4)
    window = integer(p, "window", 5, minimum=2, maximum=min(999, len(xs)))
    smooth = []
    for i in range(len(xs)):
        lo, hi = max(0, i - window // 2), min(len(xs), i + window // 2 + 1)
        smooth.append(sum(xs[lo:hi]) / (hi - lo))
    noise = [x - s for x, s in zip(xs, smooth)]
    p_signal = sum(s * s for s in smooth) / len(smooth)
    p_noise = sum(n * n for n in noise) / len(noise)
    if p_noise == 0:
        return {"snr_db": None, "note": "residual is exactly zero — no noise to measure"}
    return {"snr_db": rounded(10 * math.log10(p_signal / p_noise)),
            "signal_power": rounded(p_signal), "noise_power": rounded(p_noise),
            "definition": "signal = moving average over `window`; noise = residual"}


def peaks(p: dict[str, Any]) -> Any:
    xs = numbers(p, minimum=3)
    prominence = number(p, "min_prominence", 0.0, minimum=0.0)
    distance = integer(p, "min_distance", 1, minimum=1, maximum=len(xs))
    found = []
    for i in range(1, len(xs) - 1):
        if xs[i] > xs[i - 1] and xs[i] >= xs[i + 1]:
            left = min(xs[max(0, i - distance):i] or [xs[i]])
            right = min(xs[i + 1:i + 1 + distance] or [xs[i]])
            prom = xs[i] - max(left, right)
            if prom >= prominence:
                found.append({"index": i, "value": rounded(xs[i]), "prominence": rounded(prom)})
    kept = []
    for peak in sorted(found, key=lambda d: -d["prominence"]):
        if all(abs(peak["index"] - k["index"]) >= distance for k in kept):
            kept.append(peak)
    kept.sort(key=lambda d: d["index"])
    return {"peaks": kept, "count": len(kept)}


CATALOGUE = Catalogue(
    product_id="kyma",
    name="KYMA Signal Lab",
    description="Spectral analysis, filtering and waveform measurement over sampled signals",
    capabilities=[
        Capability("signal.spectrum@v1", "Single-sided amplitude spectrum with frequency bins from a discrete Fourier transform",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "sample_rate_hz": {"type": "number"}}},
                   OBJ, 0.012, 180, spectrum, {"series": [0, 1, 0, -1, 0, 1, 0, -1], "sample_rate_hz": 8}),
        Capability("signal.dominant-frequency@v1", "The strongest periodic component above DC, with its period and magnitude",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "sample_rate_hz": {"type": "number"}}},
                   OBJ, 0.008, 150, dominant_frequency, {"series": [0, 1, 0, -1, 0, 1, 0, -1], "sample_rate_hz": 8}),
        Capability("signal.spectral-entropy@v1", "Entropy of the power spectrum, separating a tonal signal from broadband noise",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA}},
                   OBJ, 0.010, 160, spectral_entropy, {"series": [0, 1, 0, -1, 0, 1, 0, -1]}),
        Capability("signal.band-energy@v1", "Energy and share of total energy within named frequency bands",
                   {"type": "object", "required": ["series", "bands"], "properties": {"series": SERIES_SCHEMA, "bands": {"type": "array"}, "sample_rate_hz": {"type": "number"}}},
                   OBJ, 0.012, 190, band_energy, {"series": [0, 1, 0, -1, 0, 1, 0, -1], "sample_rate_hz": 8, "bands": [[0, 2], [2, 4]]}),
        Capability("signal.rms@v1", "RMS, peak, peak-to-peak and crest factor for a waveform",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA}},
                   OBJ, 0.002, 30, rms, {"series": [1, -1, 2, -2, 3]}),
        Capability("signal.zero-crossing-rate@v1", "Zero-crossing count and rate, optionally about the series mean",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "reference": {"enum": ["zero", "mean"]}}},
                   OBJ, 0.002, 30, zero_crossing_rate, {"series": [1, -1, 1, -1, 1]}),
        Capability("signal.convolve@v1", "Discrete convolution of a signal with a kernel in full, same or valid mode",
                   {"type": "object", "required": ["signal", "kernel"], "properties": {"signal": SERIES_SCHEMA, "kernel": SERIES_SCHEMA, "mode": {"enum": ["full", "same", "valid"]}}},
                   OBJ, 0.006, 90, convolve, {"signal": [1, 2, 3, 4], "kernel": [0.5, 0.5], "mode": "same"}),
        Capability("signal.cross-correlation-lag@v1", "The lag that best aligns two series — how to measure a delay between two recordings",
                   {"type": "object", "required": ["a", "b"], "properties": {"a": SERIES_SCHEMA, "b": SERIES_SCHEMA, "max_lag": {"type": "integer"}}},
                   OBJ, 0.010, 140, cross_correlation_lag, {"a": [0, 1, 2, 1, 0, 0], "b": [0, 0, 1, 2, 1, 0]}),
        Capability("signal.median-filter@v1", "Median filter over an odd window — removes impulses a moving average would smear",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "window": {"type": "integer"}}},
                   OBJ, 0.004, 60, median_filter, {"series": [1, 1, 99, 1, 1], "window": 3}),
        Capability("signal.envelope@v1", "Upper and lower envelopes with their instantaneous width",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "window": {"type": "integer"}}},
                   OBJ, 0.004, 55, envelope, {"series": [0, 3, -3, 4, -4, 1], "window": 3}),
        Capability("signal.snr@v1", "Signal-to-noise ratio in dB, with the smoothing model stated explicitly",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "window": {"type": "integer"}}},
                   OBJ, 0.006, 80, snr, {"series": [1, 2, 1.1, 2.1, 0.9, 2.2, 1, 2]}),
        Capability("signal.peaks@v1", "Local maxima with prominence and a minimum-separation rule",
                   {"type": "object", "required": ["series"], "properties": {"series": SERIES_SCHEMA, "min_prominence": {"type": "number"}, "min_distance": {"type": "integer"}}},
                   OBJ, 0.005, 70, peaks, {"series": [0, 5, 0, 1, 0, 7, 0], "min_prominence": 1}),
    ],
)
