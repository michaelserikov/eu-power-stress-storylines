"""Event detection and event statistics: duration, severity, spatial extent, return periods, hit rates."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def runs(mask: pd.Series, merge_gap: int = 0, min_len: int = 1) -> pd.DataFrame:
    """Contiguous True runs of a boolean series on a regular index. Gaps of <= merge_gap steps are bridged."""
    m = mask.fillna(False).to_numpy(bool).copy()
    if merge_gap > 0 and m.any():
        idx = np.flatnonzero(m)
        gaps = np.diff(idx)
        for i in np.flatnonzero((gaps > 1) & (gaps <= merge_gap + 1)):
            m[idx[i] : idx[i + 1]] = True
    d = np.diff(np.r_[0, m.astype(int), 0])
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    keep = (ends - starts) >= min_len
    return pd.DataFrame({"i0": starts[keep], "i1": ends[keep]})


def exceedance_events(x: pd.Series, thr: float, merge_gap: int = 0, min_len: int = 1) -> pd.DataFrame:
    """Events where x > thr. Severity = sum of (x - thr) over the event (energy above threshold, in x-units * steps)."""
    r = runs(x > thr, merge_gap, min_len)
    v = x.to_numpy(float)
    rows = []
    for i0, i1 in zip(r.i0, r.i1):
        seg = v[i0:i1]
        ex = np.clip(seg - thr, 0, None)
        rows.append({"start": x.index[i0], "end": x.index[i1 - 1], "duration": i1 - i0,
                     "severity": float(np.nansum(ex)), "peak": float(np.nanmax(seg)), "i0": i0, "i1": i1})
    return pd.DataFrame(rows, columns=["start", "end", "duration", "severity", "peak", "i0", "i1"])


def low_events(x: pd.Series, thr: float, merge_gap: int = 0, min_len: int = 1) -> pd.DataFrame:
    """Events where x < thr (e.g. renewable output below a level); severity = sum of the deficit thr - x."""
    e = exceedance_events(-x, -thr, merge_gap, min_len)
    e["peak"] = -e["peak"]
    return e


def summarize(events: pd.DataFrame, n_years: float) -> dict:
    if events.empty:
        return {"events_per_year": 0.0, "hours_per_year": 0.0, "mean_duration_h": np.nan, "p90_duration_h": np.nan,
                "max_duration_h": 0, "mean_severity": np.nan, "max_severity": 0.0}
    return {"events_per_year": len(events) / n_years, "hours_per_year": events.duration.sum() / n_years,
            "mean_duration_h": events.duration.mean(), "p90_duration_h": events.duration.quantile(0.9),
            "max_duration_h": int(events.duration.max()), "mean_severity": events.severity.mean(),
            "max_severity": events.severity.max()}


def extent(flags: pd.DataFrame) -> pd.Series:
    """Number of countries in an event at each time step (flags: boolean frame, one column per country)."""
    return flags.sum(axis=1)


def co_occurrence(flags: pd.DataFrame) -> pd.DataFrame:
    """P(country j in event | country i in event), i in rows."""
    f = flags.astype(float)
    joint = f.T @ f
    n = np.diag(joint).copy()
    n[n == 0] = np.nan
    return joint.div(n, axis=0)


def gpd_return_levels(severities: np.ndarray, n_years: float, periods=(2, 5, 10, 20, 50),
                      q: float = 0.7) -> pd.Series:
    """Peaks-over-threshold: GPD on event severities above their q-quantile; return level for each period (years)."""
    s = np.sort(np.asarray(severities, float))
    s = s[np.isfinite(s)]
    if len(s) < 15:
        return pd.Series(np.nan, index=list(periods))
    u = np.quantile(s, q)
    exc = s[s > u] - u
    c, _, scale = stats.genpareto.fit(exc, floc=0)
    rate = len(exc) / n_years  # exceedances per year
    out = {}
    for T in periods:
        p = 1 / (rate * T)
        out[T] = u + (stats.genpareto.ppf(1 - p, c, 0, scale) if p < 1 else 0.0)
    return pd.Series(out)


def empirical_return_period(values: np.ndarray, level: float, n_years: float) -> float:
    k = int(np.sum(np.asarray(values) >= level))
    return n_years / k if k else np.inf


def daily_flags(events: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    """Daily boolean series: True on days touched by any event."""
    days = pd.Series(False, index=pd.DatetimeIndex(index.normalize().unique()))
    for s, e in zip(events.start, events.end):
        days[s.normalize() : e.normalize()] = True
    return days


def hit_rate(predicted: pd.Series, observed: pd.Series, tolerance_days: int = 1) -> dict:
    """Event-level skill: share of observed event days with a predicted day within +-tolerance (hit rate) and share of
    predicted days with no observed day within +-tolerance (false alarm ratio)."""
    predicted, observed = predicted.align(observed, join="inner", fill_value=False)
    w = 2 * tolerance_days + 1
    pred_w = predicted.astype(int).rolling(w, center=True, min_periods=1).max().astype(bool)
    obs_w = observed.astype(int).rolling(w, center=True, min_periods=1).max().astype(bool)
    hits = (observed & pred_w).sum()
    fa = (predicted & ~obs_w).sum()
    return {"observed_days": int(observed.sum()), "predicted_days": int(predicted.sum()),
            "hit_rate": hits / max(observed.sum(), 1), "false_alarm_ratio": fa / max(predicted.sum(), 1)}
