"""Net load reproduction (Bloin-Wibe et al. 2026 set-up) and WP3: stressful events, present vs SSP3-7.0.

For each fleet x heating variant x realization (A, B, C) x period (1995-2014, 2080-2099):
- European aggregate net load (copper plate) and country net load, hourly, GW;
- high-net-load hours above the 90th percentile (threshold joint over both periods and all realizations, per scenario)
  by season: the statistic of the 2026 paper;
- stress events: runs above the joint 98th percentile (gaps <= 6 h merged): frequency, duration, severity (GWh above
  threshold), GPD return levels of severity; annual maximum 7-day mean net load (storage-relevant long events);
- spatial extent: number of countries simultaneously above their own 98th percentile; co-occurrence.
Outputs: results/wp3/*.csv, figures/wp3_*.png.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stress import events as ev
from stress import system as sy
from stress.pipeline import PERIODS, REALS, SEASON, compute_netload, demand_from, load_inputs
from stress.paths import DERIVED, FIGURES, RESULTS

OUT = RESULTS / "wp3"
OUT.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(exist_ok=True)


def main():
    profile, cs, data = load_inputs()
    has_off = set(data[("A", "historical")]["cf"]["wind_off"].columns)
    summary, seasonal, rl_rows, ext_rows, amax_rows = [], [], [], [], []
    for heat_key in ["heat", "heat_full"]:
        ann = demand_from(data[("A", "historical")], profile, heat_key).mean()
        fleets = sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), has_off)
        fleets.pop("current")
        cur = DERIVED / "current_fleet_energy.csv"
        if cur.exists():
            fleets["current"] = sy.Fleet("current", pd.read_csv(cur, index_col=0).reindex(ann.index).fillna(0))
        nl = compute_netload(profile, cs, data, fleets, heat_key)
        for fname in fleets:
            eu = {(r, p): nl[(fname, r, p)].sum(axis=1) for r in REALS for p in PERIODS}
            pooled = pd.concat(eu.values())
            t90, t98 = pooled.quantile(0.90), pooled.quantile(0.98)
            # country thresholds for extent
            cthr = pd.concat([nl[(fname, r, p)] for r in REALS for p in PERIODS]).quantile(0.98)
            for r in REALS:
                for p in PERIODS:
                    x = eu[(r, p)]
                    yrs = len(x) / 8760
                    hi = x > t90
                    for s in ["DJF", "MAM", "JJA", "SON"]:
                        m = x.index.month.map(SEASON) == s
                        seasonal.append({"heat": heat_key, "fleet": fname, "real": r, "period": p, "season": s,
                                         "hours_above_p90_per_year": hi[m].sum() / yrs})
                    seasonal.append({"heat": heat_key, "fleet": fname, "real": r, "period": p, "season": "year",
                                     "hours_above_p90_per_year": hi.sum() / yrs})
                    e = ev.exceedance_events(x, t98, merge_gap=6)
                    st = ev.summarize(e, yrs)
                    st.update({"heat": heat_key, "fleet": fname, "real": r, "period": p, "p98_GW": t98,
                               "mean_netload_GW": x.mean(), "p99_9_GW": x.quantile(0.999)})
                    summary.append(st)
                    rl = ev.gpd_return_levels(e.severity.to_numpy(), yrs, periods=(2, 5, 10, 20))
                    rl_rows.append({"heat": heat_key, "fleet": fname, "real": r, "period": p,
                                    **{f"severity_rl{k}y_TWh": v / 1000 for k, v in rl.items()}})
                    w7 = x.rolling(168).mean()
                    am = w7.groupby(w7.index.year).max().dropna()
                    am = am[am.index.map(lambda y: (x.index.year == y).sum() > 8000)]
                    amax_rows.append({"heat": heat_key, "fleet": fname, "real": r, "period": p,
                                      "mean_annual_max_7d_GW": am.mean(), "max_7d_GW": am.max()})
                    flags = nl[(fname, r, p)] > cthr
                    extent = flags.sum(axis=1)
                    ext_rows.append({"heat": heat_key, "fleet": fname, "real": r, "period": p,
                                     "hours_with_>=5_countries_per_year": (extent >= 5).sum() / yrs,
                                     "hours_with_>=10_countries_per_year": (extent >= 10).sum() / yrs,
                                     "mean_extent_when_eu_event": extent[x > t98].mean()})
            if heat_key == "heat" and fname == "balanced":
                co = {p: ev.co_occurrence(pd.concat([nl[(fname, r, p)] > cthr for r in REALS])) for p in PERIODS}
                co["historical"].to_csv(OUT / "cooccurrence_balanced_hist.csv")
                co["SSP370"].to_csv(OUT / "cooccurrence_balanced_ssp370.csv")
            if heat_key == "heat" and fname == "high_wind":
                # save EU net load for later work packages
                pd.DataFrame({f"{r}_{p}": eu[(r, p)].reset_index(drop=True) for r in REALS for p in PERIODS}
                             ).to_parquet(DERIVED / "eu_netload_highwind_heat.parquet")
    pd.DataFrame(summary).to_csv(OUT / "event_summary.csv", index=False)
    sea = pd.DataFrame(seasonal)
    sea.to_csv(OUT / "hours_above_p90.csv", index=False)
    pd.DataFrame(rl_rows).to_csv(OUT / "severity_return_levels.csv", index=False)
    pd.DataFrame(ext_rows).to_csv(OUT / "spatial_extent.csv", index=False)
    pd.DataFrame(amax_rows).to_csv(OUT / "annual_max_7day.csv", index=False)
    # change table (pooled over realizations) and spread
    piv = sea.pivot_table(index=["heat", "fleet", "season", "real"], columns="period",
                          values="hours_above_p90_per_year")
    piv["change_pct"] = 100 * (piv["SSP370"] / piv["historical"] - 1)
    piv.to_csv(OUT / "p90_change_by_realization.csv")
    pooled = sea.groupby(["heat", "fleet", "season", "period"]).hours_above_p90_per_year.mean().unstack()
    pooled["change_pct"] = 100 * (pooled["SSP370"] / pooled["historical"] - 1)
    rng = piv.groupby(level=[0, 1, 2]).change_pct.agg(["min", "max"])
    pooled = pooled.join(rng)
    pooled.to_csv(OUT / "p90_change_pooled.csv")
    print(pooled.round(1).to_string())
    plot(pooled)


def plot(pooled):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    seasons = ["DJF", "MAM", "JJA", "SON", "year"]
    for ax, heat in zip(axes, ["heat", "heat_full"]):
        sub = pooled.loc[heat]
        fleets = list(sub.index.get_level_values(0).unique())
        w = 0.8 / len(fleets)
        for i, f in enumerate(fleets):
            s = sub.loc[f].reindex(seasons)
            x = np.arange(len(seasons)) + i * w
            ax.bar(x, s["change_pct"], w, label=f.replace("_", " "))
            ax.errorbar(x, s["change_pct"], yerr=[s["change_pct"] - s["min"], s["max"] - s["change_pct"]],
                        fmt="none", ecolor="k", lw=0.8)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xticks(np.arange(len(seasons)) + 0.4 - w / 2, seasons)
        ax.set_title("current heating" if heat == "heat" else "fully electrified heating")
    axes[0].set_ylabel("change in hours above P90 (%)\n2080-2099 SSP3-7.0 vs 1995-2014")
    axes[1].legend(fontsize=8)
    fig.suptitle("European net load: high-net-load hours, mean of 3 realizations (bars: range)", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "wp3_p90_change.png", dpi=150)


if __name__ == "__main__":
    main()
