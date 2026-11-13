"""Nordic hydrology: dry inflow years in Norway and Sweden together with continental stress winters.

C2E: weekly reservoir inflow (GWh) for NO and SE, realizations A, B, C, 1995-2014 and 2080-2099.
- inflow year = September to August; dry year = below the present-day 20th percentile (pooled over realizations);
- continental stress winter = top 20% of winters (November-March) by energy of European net load (balanced fleet,
  current heating, Nordic countries excluded) above its present-day 98th percentile;
- compound = a dry inflow year whose following winter is a stress winter; ratio to independence (0.2 x 0.2).
Observed check: NVE Norwegian reservoir filling at ISO week 40 (early October, 1995-2025) against the ERA5
weather-only stress index of the following winter (WP1, today's fleet).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stress import system as sy
from stress.paths import DERIVED, FIGURES, RESULTS
from stress.pipeline import PERIODS, REALS, compute_netload, demand_from, load_inputs

OUT = RESULTS / "v03"
OUT.mkdir(parents=True, exist_ok=True)
NVE = Path(os.environ.get("NVE_JSON", Path.home() / "nordic-hydro-unit-commitment" / "data" / "raw" / "nve_magasinstatistikk.json"))
NORDIC = {"NO", "SE", "FI"}


def hydro_year(idx):
    return idx.year + (idx.month >= 9)  # September-August, labelled by the year it ends


def winter_of(idx):
    return idx.year + (idx.month >= 9)  # winter Nov-Mar labelled by its January year


def main():
    profile, cs, data = load_inputs()
    has_off = set(data[("A", "historical")]["cf"]["wind_off"].columns)
    ann = demand_from(data[("A", "historical")], profile, "heat").mean()
    fl = {"balanced": sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), has_off)["balanced"]}
    nl = compute_netload(profile, cs, data, fl, "heat")
    cont = [c for c in cs if c not in NORDIC]
    eu = {(r, p): nl[("balanced", r, p)][cont].sum(axis=1) for r in REALS for p in PERIODS}
    thr = pd.concat([eu[(r, "historical")] for r in REALS]).quantile(0.98)
    inflow, stress = {}, {}
    for r in REALS:
        for p in PERIODS:
            inf = sy.c2e_frame("inflow", r, p)[["NO", "SE"]]
            hy = inf.groupby(hydro_year(inf.index)).sum() / 1000  # TWh
            hy = hy.iloc[1:-1] if len(hy) > 2 else hy  # drop incomplete first and last hydro years
            inflow[(r, p)] = hy
            x = eu[(r, p)]
            w = x[x.index.month.isin([11, 12, 1, 2, 3])]
            e = (w - thr).clip(lower=0).groupby(winter_of(w.index)).sum() / 1000  # TWh
            stress[(r, p)] = e
    dry_thr = pd.concat([inflow[(r, "historical")] for r in REALS]).quantile(0.2)
    st_thr = pd.concat([stress[(r, "historical")] for r in REALS]).quantile(0.8)
    rows = []
    for (r, p), hy in inflow.items():
        s = stress[(r, p)]
        for c in ["NO", "SE"]:
            dry = hy[c] < dry_thr[c]
            # dry year ending in August y, stress winter labelled y+1 (Nov y - Mar y+1)
            nxt = s.reindex(hy.index + 1)
            sw = (nxt >= st_thr).to_numpy()
            ok = ~np.isnan(nxt.to_numpy())
            joint = (dry.to_numpy() & sw & ok).sum() / ok.sum()
            rows.append({"real": r, "period": p, "country": c, "mean_inflow_TWh": hy[c].mean(),
                         "cv_inflow": hy[c].std() / hy[c].mean(), "dry_year_freq": dry.mean(),
                         "stress_winter_freq": float(np.nanmean(sw[ok])), "joint_freq": joint,
                         "ratio_to_independence": joint / max(dry.mean() * np.nanmean(sw[ok]), 1e-9),
                         "corr_inflow_next_winter_stress": np.corrcoef(hy[c].to_numpy()[ok], nxt.to_numpy()[ok])[0, 1]})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "nordic_hydro_compound.csv", index=False)
    print(df.round(3).to_string())
    print(df.drop(columns="real").groupby(["country", "period"]).mean().round(3).to_string())
    observed()
    plot(inflow, df)


def observed():
    if not NVE.exists():
        print("NVE file not found, observed check skipped")
        return
    d = pd.DataFrame(json.loads(NVE.read_text(encoding="utf-8")))
    d = d[d["omrType"] == "NO"]
    d = d[d["iso_uke"] == 40][["iso_aar", "fyllingsgrad"]].rename(columns={"iso_aar": "year", "fyllingsgrad": "fill_share"})
    d = d.set_index("year")["fill_share"].sort_index()
    idx = pd.read_parquet(DERIVED / "era5_stress_index_daily.parquet")["stress_index_GW"]
    w = idx[idx.index.month.isin([11, 12, 1, 2, 3])]
    thr = idx.loc["1991":"2020"].quantile(0.97)
    sw = (w >= thr).groupby(winter_of(w.index)).sum()
    t = pd.DataFrame({"nve_fill_week40": d, "stress_days_next_winter": sw.reindex(d.index + 1).to_numpy()}, index=d.index)
    t = t.dropna()
    t.to_csv(OUT / "nve_fill_vs_next_winter.csv")
    res = {"years": len(t), "spearman": t.corr(method="spearman").iloc[0, 1],
           "low_fill_years": ", ".join(str(y) for y in t.nsmallest(5, "nve_fill_week40").index),
           "stress_days_after_low_fill_mean": t.nsmallest(6, "nve_fill_week40").stress_days_next_winter.mean(),
           "stress_days_all_mean": t.stress_days_next_winter.mean()}
    pd.Series(res).to_csv(OUT / "nve_observed_summary.csv", header=["value"])
    print(res)


def plot(inflow, df):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for r, m in zip(REALS, ["o", "s", "^"]):
        for p, col in zip(PERIODS, ["tab:blue", "tab:red"]):
            hy = inflow[(r, p)]["NO"]
            axes[0].hist(hy, bins=10, histtype="step", color=col, alpha=0.7, label=f"{p} {r}")
    axes[0].set_xlabel("Norwegian annual inflow, Sep-Aug (TWh)")
    axes[0].legend(fontsize=6)
    g = df.groupby(["country", "period"]).ratio_to_independence.agg(["mean", "min", "max"])
    lab = [f"{c} {p}" for c, p in g.index]
    axes[1].bar(range(len(g)), g["mean"], yerr=[g["mean"] - g["min"], g["max"] - g["mean"]], color="0.6")
    axes[1].axhline(1, color="k", lw=0.6)
    axes[1].set_xticks(range(len(g)), lab, fontsize=8)
    axes[1].set_ylabel("dry year then stress winter\n(ratio to independence)")
    fig.tight_layout()
    fig.savefig(FIGURES / "v03_nordic_hydro.png", dpi=150)


if __name__ == "__main__":
    main()
