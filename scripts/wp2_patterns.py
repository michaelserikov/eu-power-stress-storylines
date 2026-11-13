"""WP2: weather patterns behind stressful periods and their analogues in the future climate.

1. Regimes: four winter (NDJFM) weather regimes from ERA5 daily MSLP 1990-2025 (EOF + k-means), named by their
   anomaly centres. Regime frequency on the top-3% days of the weather-only stress index (WP1) vs all winter days,
   with a bootstrap over winters; trend of the stress-regime frequency 1990-2025.
2. Composites: MSLP anomaly of the stress days and of the named events, pattern correlation with each regime.
3. Analogues in CESM2: the Climate2Energy archive holds no pressure fields, so analogues are searched on the spatial
   pattern of the drivers themselves: 3-day mean standardized anomalies of onshore wind, PV and temperature-driven
   demand in 32 countries (ERA5: C3S wind, PV and minus 2 m temperature; C2E: wind, PV and heating + cooling demand,
   standardized against each dataset's own present-day climate). For each named event: how often days within the
   analogue distance occur in 1995-2014 vs 2080-2099 per realization, and how high European net load is on them.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import kendalltau, theilslopes

from stress import obs
from stress import regimes as rg
from stress import system as sy
from stress.paths import DERIVED, FIGURES, RESULTS
from stress.pipeline import PERIODS, REALS, compute_netload, demand_from, load_inputs

OUT = RESULTS / "wp2"
OUT.mkdir(parents=True, exist_ok=True)
STORYLINES = {"Jan 2017 cold spell": "2017-01-20", "Nov 2024 Dunkelflaute": "2024-11-06",
              "Dec 2024 Dunkelflaute": "2024-12-12"}
WINTER = [11, 12, 1, 2, 3]
RNG = np.random.default_rng(3)


def regimes_part():
    field, lat, lon, days = rg.daily_mslp(1990, 2025)
    anom = rg.anomalies(field, days)
    w = np.isin(days.month, WINTER)
    labels, maps, expl = rg.eof_kmeans(anom[w], lat, k=4)
    names = rg.name_regimes(maps, lat, lon)
    reg = pd.Series([names[i] for i in labels], index=days[w])
    reg.to_frame("regime").to_csv(OUT / "regimes_daily.csv")
    idx = pd.read_parquet(DERIVED / "era5_stress_index_daily.parquet")["stress_index_GW"]
    idx = idx.reindex(reg.index)
    stress = idx >= idx.quantile(0.97)
    winters = reg.index.year + (reg.index.month >= 7)
    rows = []
    for n in sorted(set(names)):
        share_all = (reg == n).mean()
        share_stress = (reg[stress] == n).mean()
        boot = []
        uw = np.unique(winters)
        pos = {k: np.flatnonzero(winters == k) for k in uw}
        for _ in range(1000):
            pick = np.concatenate([pos[k] for k in RNG.choice(uw, len(uw))])  # whole winters, with replacement
            r_, s_ = reg.iloc[pick], stress.iloc[pick]
            boot.append((r_[s_] == n).mean() / max((r_ == n).mean(), 1e-9))
        rows.append({"regime": n, "share_all_winter_days": share_all, "share_stress_days": share_stress,
                     "rate_ratio": share_stress / share_all, "ratio_p05": np.quantile(boot, 0.05),
                     "ratio_p95": np.quantile(boot, 0.95)})
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "regime_vs_stress.csv", index=False)
    # trend of the most stress-prone regime's winter frequency
    top = tab.sort_values("rate_ratio").regime.iloc[-1]
    freq = (reg == top).groupby(winters).mean()
    freq = freq[(freq.index > 1990) & (freq.index <= 2025)]
    tau, p = kendalltau(freq.index, freq.to_numpy())
    slope = theilslopes(freq.to_numpy(), freq.index)[0]
    trend = {"regime": top, "kendall_tau": tau, "p": p, "sen_per_decade_pct_points": 1000 * slope}
    pd.Series(trend).to_csv(OUT / "stress_regime_trend.csv", header=["value"])
    # composites
    stress_comp = anom[w][stress.to_numpy()].mean(axis=0)
    comps = {"top-3% stress days": stress_comp}
    for name, d in STORYLINES.items():
        k = np.flatnonzero(days == pd.Timestamp(d))
        if len(k):
            comps[name] = anom[max(k[0] - 1, 0): k[0] + 2].mean(axis=0)
    pc = pd.DataFrame({c: {n: rg.pattern_corr(m, maps[i], lat) for i, n in enumerate(names)} for c, m in comps.items()})
    pc.to_csv(OUT / "composite_pattern_corr.csv")
    print(tab.round(3).to_string())
    print(trend)
    print(pc.round(2).to_string())
    plot_maps(comps, maps, names, lat, lon)
    return reg


def plot_maps(comps, maps, names, lat, lon):
    n = len(comps) + len(maps)
    fig, axes = plt.subplots(2, max(len(comps), len(maps)), figsize=(3.2 * max(len(comps), len(maps)), 5.8))
    lev = np.arange(-24, 25, 3)
    for ax, (t, m) in zip(axes[0], list(comps.items())):
        cs = ax.contourf(lon, lat, m, levels=lev, cmap="RdBu_r", extend="both")
        ax.set_title(t, fontsize=8)
    for ax, t, m in zip(axes[1], names, maps):
        ax.contourf(lon, lat, m, levels=lev, cmap="RdBu_r", extend="both")
        ax.set_title(f"regime: {t}", fontsize=8)
    land = land_mask()
    for ax in axes.ravel():
        if land is not None:
            ax.contour(land[1], land[0], land[2], levels=[0.5], colors="k", linewidths=0.4)
        ax.set_xlim(-60, 40)
        ax.set_ylim(30, 75)
        ax.tick_params(labelsize=6)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    fig.colorbar(cs, ax=axes, shrink=0.6, label="MSLP anomaly (hPa)")
    fig.suptitle("ERA5 MSLP anomalies: stress days, named events (top) and winter regimes (bottom)", fontsize=10)
    fig.savefig(FIGURES / "wp2_composites_regimes.png", dpi=140, bbox_inches="tight")


def land_mask():
    """Coarse land outline (0.5 deg) from the CLIMADA national ID raster, for orientation only."""
    import os
    from pathlib import Path

    import xarray as xr
    path = Path(os.environ.get("NATID_GRID", Path.home() / "climada" / "data" / "NatID_grid_0150as.nc"))
    if not path.exists():
        return None
    g = xr.open_dataset(path)["NatIdGrid"].sel(lat=slice(25, 80), lon=slice(-65, 45))[::12, ::12]
    return g.lat.to_numpy(), g.lon.to_numpy(), (g.to_numpy() > 0).astype(float)


def driver_patterns():
    """3-day mean standardized anomalies, columns var_country."""
    cs = obs.C2E_COUNTRIES
    era = {"wind": obs.c3s("wind_on")[cs].resample("1D").mean(), "pv": obs.c3s("pv")[cs].resample("1D").mean(),
           "dem": -obs.c3s("t2m")[cs].resample("1D").mean()}
    ref = slice("1991-01-01", "2020-12-31")
    e = pd.concat({k: rg.standardized(v.loc["1979":"2025"], v.loc[ref]) for k, v in era.items()}, axis=1)
    e = e.rolling(3, center=True).mean()
    c2e = {}
    for r in REALS:
        raw = {p: {"wind": sy.c2e_frame("wind_on", r, p)[cs].resample("1D").mean(),
                   "pv": sy.c2e_frame("pv", r, p)[cs].resample("1D").mean(),
                   "dem": (sy.c2e_frame("heat", r, p)[cs] + sy.c2e_frame("cool", r, p)[cs]).resample("1D").mean()}
               for p in PERIODS}
        for p in PERIODS:
            x = pd.concat({k: rg.standardized(raw[p][k], raw["historical"][k]) for k in raw[p]}, axis=1)
            c2e[(r, p)] = x.rolling(3, center=True).mean()
    return e, c2e


def analogues_part():
    e, c2e = driver_patterns()
    profile, cs, data = load_inputs()
    has_off = set(data[("A", "historical")]["cf"]["wind_off"].columns)
    ann = demand_from(data[("A", "historical")], profile, "heat").mean()
    fl = {"balanced": sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), has_off)["balanced"]}
    nl = compute_netload(profile, cs, data, fl, "heat")
    eu = {(r, p): nl[("balanced", r, p)].sum(axis=1).resample("1D").mean().rolling(3, center=True).mean()
          for r in REALS for p in PERIODS}
    p98 = pd.concat(eu.values()).quantile(0.98)
    rows = []
    for name, d in STORYLINES.items():
        target = e.loc[d].to_numpy()
        doy = pd.Timestamp(d).day_of_year
        dist = {}
        for key, x in c2e.items():
            dd = np.sqrt(np.nanmean((x.to_numpy() - target) ** 2, axis=1))
            ser = pd.Series(dd, x.index)
            cal = np.abs(((x.index.day_of_year - doy + 183) % 366) - 183) <= 45
            dist[key] = ser[cal].dropna()
        thr = np.quantile(pd.concat([dist[(r, "historical")] for r in REALS]), 0.01)
        for (r, p), ser in dist.items():
            hit = ser[ser <= thr]
            # decluster: one analogue per 5 days
            kept, last = [], None
            for t in hit.sort_values().index:
                if last is None or all(abs((t - k).days) > 5 for k in kept):
                    kept.append(t)
            nyr = len(np.unique(ser.index.year))
            v = eu[(r, p)].reindex(kept)
            rows.append({"event": name, "real": r, "period": p, "analogue_days_per_decade": 10 * len(hit) / nyr,
                         "analogue_episodes_per_decade": 10 * len(kept) / nyr, "closest_distance": ser.min(),
                         "analogue_threshold": thr, "mean_eu_netload_on_analogues_GW": v.mean(),
                         "max_eu_netload_on_analogues_GW": v.max(), "share_above_p98": float((v > p98).mean()) if len(v) else np.nan})
        # how close was the ERA5 event to its own climate: distance distribution in ERA5 itself
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "analogues_c2e.csv", index=False)
    piv = tab.pivot_table(index="event", columns="period",
                          values=["analogue_episodes_per_decade", "mean_eu_netload_on_analogues_GW"], aggfunc="mean")
    rng = tab.pivot_table(index="event", columns="period", values="analogue_episodes_per_decade", aggfunc=["min", "max"])
    piv.to_csv(OUT / "analogues_summary.csv")
    rng.to_csv(OUT / "analogues_range.csv")
    print(tab.round(2).to_string())
    print(piv.round(2).to_string())


if __name__ == "__main__":
    regimes_part()
    analogues_part()
