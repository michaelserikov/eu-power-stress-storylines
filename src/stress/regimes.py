"""Weather regimes from ERA5 mean sea level pressure and analogue search on country anomaly patterns."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.vq import kmeans2

from .paths import MSLP

ORIGIN = pd.Timestamp("1900-01-01")


def daily_mslp(start=1990, end=2025) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Daily mean MSLP (hPa) on the 1.5 deg North Atlantic-European grid of the cached ERA5 files."""
    fields, days = [], []
    lat = lon = None
    for y in range(start, end + 1):
        d = np.load(MSLP / f"mslp_{y}.npz")
        lat, lon = d["lat"], d["lon"]
        t = ORIGIN + pd.to_timedelta(d["time"], unit="h")
        day = t.floor("D")
        msl = d["msl"].astype("float32") / 100.0
        for k in pd.unique(day):
            fields.append(msl[day == k].mean(axis=0))
            days.append(k)
    return np.stack(fields), lat, lon, pd.DatetimeIndex(days)


def anomalies(field: np.ndarray, days: pd.DatetimeIndex, half_window: int = 15) -> np.ndarray:
    """Anomalies from a +-15-day calendar climatology."""
    doy = days.day_of_year.to_numpy()
    clim = np.empty((366,) + field.shape[1:], dtype="float32")
    for d in range(1, 367):
        near = np.abs(((doy - d + 183) % 366) - 183) <= half_window
        clim[d - 1] = field[near].mean(axis=0)
    return field - clim[doy - 1]


def eof_kmeans(anom: np.ndarray, lat: np.ndarray, n_pcs: int = 10, k: int = 4, seed: int = 7):
    """EOF truncation (cos-latitude weighted) then k-means; returns labels, centroids (anomaly maps), explained var."""
    w = np.sqrt(np.cos(np.deg2rad(lat)))[None, :, None]
    x = (anom * w).reshape(len(anom), -1)
    x = x - x.mean(axis=0)
    u, s, vt = np.linalg.svd(x, full_matrices=False)
    pcs = u[:, :n_pcs] * s[:n_pcs]
    best = None
    for trial in range(10):  # several k-means starts, keep the lowest within-cluster variance
        cent, lab = kmeans2(pcs, k, seed=seed + trial, minit="++", iter=200)
        inertia = sum(((pcs[lab == j] - cent[j]) ** 2).sum() for j in range(k))
        if best is None or inertia < best[0]:
            best = (inertia, lab)
    labels = best[1]
    maps = np.stack([anom[labels == j].mean(axis=0) for j in range(k)])
    return labels, maps, (s**2 / (s**2).sum())[:n_pcs]


def name_regimes(maps: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> list[str]:
    """Heuristic names from the anomaly centres: NAO+ (low north, high south), NAO- (opposite),
    Scandinavian blocking (high over Scandinavia), Atlantic ridge (high over the central/eastern Atlantic)."""
    def box(m, la, lo):
        a = (lat >= la[0]) & (lat <= la[1])
        b = (lon >= lo[0]) & (lon <= lo[1])
        return m[np.ix_(a, b)].mean()

    names = []
    for m in maps:
        north, south = box(m, (60, 75), (-40, 0)), box(m, (35, 50), (-40, 0))
        scand = box(m, (55, 70), (5, 35))
        atl = box(m, (45, 60), (-35, -15))
        scores = {"NAO+": south - north, "NAO-": north - south, "Scandinavian blocking": scand,
                  "Atlantic ridge": atl}
        names.append(max(scores, key=scores.get))
    # make names unique by order of score if duplicates
    seen = {}
    out = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
    return out


def pattern_corr(a: np.ndarray, b: np.ndarray, lat: np.ndarray) -> float:
    w = np.cos(np.deg2rad(lat))[:, None] * np.ones_like(a)
    a0, b0 = a - np.average(a, weights=w), b - np.average(b, weights=w)
    return float(np.sum(w * a0 * b0) / np.sqrt(np.sum(w * a0**2) * np.sum(w * b0**2)))


def standardized(df: pd.DataFrame, ref: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily anomalies from the reference calendar climatology, mapped through the reference anomaly distribution to
    standard normal scores. With ref = present-day data, future values keep their shift relative to today."""
    from scipy.stats import norm
    ref = df if ref is None else ref
    clim = ref.groupby(ref.index.day_of_year).mean()
    ra = ref - clim.reindex(ref.index.day_of_year).to_numpy()
    a = df - clim.reindex(df.index.day_of_year).to_numpy()
    out = {}
    for c in df.columns:
        srt = np.sort(ra[c].dropna().to_numpy())
        p = (np.searchsorted(srt, a[c].to_numpy(), side="right") + 0.5) / (len(srt) + 1)
        out[c] = norm.ppf(np.clip(p, 1e-4, 1 - 1e-4))
    return pd.DataFrame(out, index=df.index)
