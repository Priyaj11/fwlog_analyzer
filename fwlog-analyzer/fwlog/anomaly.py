"""Statistical anomaly detection on task timing.

Deadline logic (analysis.py) catches gross violations against a known model.
This module is complementary: it flags *statistical* outliers in the timing
series without assuming a threshold, which catches slow drift and rare spikes
a fixed rule would miss.

Two detectors are provided:

* rolling z-score   - classic, but sensitive to the very outliers it should be
                      detecting (they inflate the running std-dev).
* rolling MAD/z     - median + median-absolute-deviation, a robust estimator
                      (breakdown point ~50%). This is the recommended detector
                      for spiky embedded timing data.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Anomaly:
    index: int          # position in the series
    value: float
    score: float        # signed z / robust-z score
    method: str


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])


def rolling_zscore(series: list[float], window: int = 20, thresh: float = 3.0) -> list[Anomaly]:
    """Flag points whose value is `thresh` sample std-devs from the trailing mean."""
    out: list[Anomaly] = []
    for i in range(len(series)):
        lo = max(0, i - window)
        ref = series[lo:i]
        if len(ref) < max(3, window // 2):
            continue
        mean = sum(ref) / len(ref)
        var = sum((x - mean) ** 2 for x in ref) / (len(ref) - 1)
        std = var ** 0.5
        if std == 0:
            # Zero-variance baseline: any departure is, by definition, a
            # deviation of infinite sigma. Flag it rather than silently skip.
            if abs(series[i] - mean) > 1e-12:
                out.append(Anomaly(i, series[i], float("inf"), "zscore"))
            continue
        z = (series[i] - mean) / std
        if abs(z) >= thresh:
            out.append(Anomaly(i, series[i], z, "zscore"))
    return out


def rolling_mad(series: list[float], window: int = 20, thresh: float = 3.5) -> list[Anomaly]:
    """Robust detector using median and MAD.

    robust_z = 0.6745 * (x - median) / MAD, where 0.6745 rescales MAD to be a
    consistent estimator of sigma for normal data. Iglewicz & Hoaglin recommend
    a threshold near 3.5.
    """
    out: list[Anomaly] = []
    for i in range(len(series)):
        lo = max(0, i - window)
        ref = series[lo:i]
        if len(ref) < max(3, window // 2):
            continue
        med = _median(ref)
        mad = _median([abs(x - med) for x in ref])
        if mad == 0:
            # Degenerate scale estimate (e.g. flat baseline). Fall back to
            # flagging any nonzero departure from the median.
            if abs(series[i] - med) > 1e-12:
                out.append(Anomaly(i, series[i], float("inf"), "mad"))
            continue
        rz = 0.6745 * (series[i] - med) / mad
        if abs(rz) >= thresh:
            out.append(Anomaly(i, series[i], rz, "mad"))
    return out


def detect(series: list[float], method: str = "mad", **kw) -> list[Anomaly]:
    if method == "zscore":
        return rolling_zscore(series, **kw)
    if method == "mad":
        return rolling_mad(series, **kw)
    raise ValueError(f"unknown method: {method}")
