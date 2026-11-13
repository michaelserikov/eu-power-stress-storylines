"""WP1c: does bias-corrected CESM2 (Climate2Energy historical, 3 realizations) reproduce ERA5 event statistics?

ERA5 side: C3S ERA5-based country capacity factors (sis-energy-derived-reanalysis) and C3S daily demand, 1995-2014.
C2E side: Climate2Energy historical 1995-2014, realizations A, B, C. Both are normalised by their own mean, because
the two use different conversion models (turbines, PV model); the comparison is about time structure.

C2E corrects each grid box's marginal distribution against ERA5 (univariate quantile mapping), so marginals should
agree by construction. What it does not constrain: persistence, spatial coherence across countries and the joint
behaviour of wind and demand. These are what stressful events depend on, and what this script tests.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stress import events as ev
from stress import obs
from stress import system as sy
from stress.paths import FIGURES, RESULTS

OUT = RESULTS / "wp1"
OUT.mkdir(parents=True, exist_ok=True)
P = slice("1995-01-01", "2014-12-31")
CS = ["AT", "BE", "CZ", "DE", "DK", "ES", "FI", "FR", "GB", "GR", "IE", "IT", "NL", "NO", "PL", "PT", "RO", "SE"]


def daily(df):
    return df.resample("1D").mean()


def lowrun_stats(x: pd.Series, thr=0.1, min_len=2):
    """Low-output spells: consecutive days with daily output (as percentile) below thr (>= min_len days)."""
    e = ev.low_events(x, thr, min_len=min_len)
    yrs = len(x) / 365.25
    return {"spells_per_year": len(e) / yrs, "days_per_year": e.duration.sum() / yrs,
            "mean_len_d": e.duration.mean() if len(e) else 0, "max_len_d": e.duration.max() if len(e) else 0}


def main():
    era = {t: daily(obs.c3s(t).loc[P]) for t in ("wind_on", "pv", "wind_off")}
    dem_era = obs.c3s("demand_daily").loc[P]
    c2e = {}
    for r in "ABC":
        c2e[r] = {t: daily(sy.c2e_frame(t, r, "historical").loc[P]) for t in ("wind_on", "pv", "wind_off")}
        hd = sy.c2e_frame("heat", r, "historical").loc[P]
        cd = sy.c2e_frame("cool", r, "historical").loc[P]
        c2e[r]["tsdem"] = daily(hd + cd.reindex(hd.index).fillna(0))
    rows, corr_rows = [], []
    # ---- per-country statistics
    for c in CS:
        for src, data in [("ERA5", era)] + [(f"C2E-{r}", c2e[r]) for r in "ABC"]:
            wraw = data["wind_on"][c] / data["wind_on"][c].mean()
            pv = data["pv"][c] / data["pv"][c].mean()
            # rank transform: daily output as its own percentile, invariant to the (monotone) power-curve choice
            w = wraw.rank(pct=True)
            port = (0.6 * wraw + 0.4 * pv).rank(pct=True)  # balanced portfolio
            row = {"country": c, "source": src, "wind_cv_daily_raw": wraw.std(),
                   "wind_acf1_daily": w.autocorr(1), "wind_acf3_daily": w.autocorr(3),
                   "pv_djf_mean_rel": pv[pv.index.month.isin([12, 1, 2])].mean()}
            row.update({f"wind_low_{k}": v for k, v in lowrun_stats(w, 0.10).items()})
            row.update({f"port_low_{k}": v for k, v in lowrun_stats(port, 0.05).items()})
            # compound: winter wind vs temperature-sensitive demand (ERA5: C3S demand; C2E: heating+cooling)
            if src == "ERA5":
                d = dem_era[c] if c in dem_era else None
            else:
                d = data["tsdem"][c]
            if d is not None:
                wj = w[w.index.month.isin([12, 1, 2])]
                dj = d.reindex(wj.index)
                # remove the seasonal cycle (day-of-winter mean) from both before correlating
                key = wj.index.day_of_year
                wa = wj - wj.groupby(key).transform("mean")
                da = dj - dj.groupby(key).transform("mean")
                row["djf_corr_wind_demand"] = wa.corr(da, method="spearman")
            rows.append(row)
    stats = pd.DataFrame(rows)
    stats.to_csv(OUT / "era5_vs_c2e_country_stats.csv", index=False)
    # ---- spatial coherence: correlation matrices of daily wind anomalies
    def anom_corr(df):
        a = df[CS].rank(pct=True)
        a = a - a.groupby(a.index.day_of_year).transform("mean")
        return a.corr()

    ce = anom_corr(era["wind_on"])
    iu = np.triu_indices(len(CS), 1)
    for r in "ABC":
        cc = anom_corr(c2e[r]["wind_on"])
        corr_rows.append({"source": f"C2E-{r}", "mean_pair_corr": cc.to_numpy()[iu].mean(),
                          "mean_abs_diff_vs_era5": np.abs(cc.to_numpy()[iu] - ce.to_numpy()[iu]).mean(),
                          "pattern_corr_vs_era5": np.corrcoef(cc.to_numpy()[iu], ce.to_numpy()[iu])[0, 1]})
    corr_rows.insert(0, {"source": "ERA5", "mean_pair_corr": ce.to_numpy()[iu].mean(), "mean_abs_diff_vs_era5": 0,
                         "pattern_corr_vs_era5": 1})
    pd.DataFrame(corr_rows).to_csv(OUT / "era5_vs_c2e_spatial_coherence.csv", index=False)
    # ---- European aggregate: low-wind spells of the continental pool (pooling benefit)
    agg_rows = []
    for src, data in [("ERA5", era)] + [(f"C2E-{r}", c2e[r]) for r in "ABC"]:
        w = (data["wind_on"][CS] / data["wind_on"][CS].mean()).mean(axis=1).rank(pct=True)
        agg_rows.append({"source": src, **lowrun_stats(w, 0.10), "acf1": w.autocorr(1)})
    pd.DataFrame(agg_rows).to_csv(OUT / "era5_vs_c2e_european_pool.csv", index=False)
    # ---- summary table: C2E relative to ERA5
    num = stats.drop(columns=["country"]).groupby("source").median()
    num.to_csv(OUT / "era5_vs_c2e_median_over_countries.csv")
    print(num.T.round(3).to_string())
    print(pd.DataFrame(corr_rows).round(3).to_string())
    print(pd.DataFrame(agg_rows).round(3).to_string())
    plot(stats)


def plot(stats):
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, col, lab in zip(axes, ["wind_acf1_daily", "wind_low_days_per_year", "djf_corr_wind_demand"],
                            ["lag-1 day autocorrelation, onshore wind", "days/yr in low-wind spells (< own P10, >=2 d)",
                             "winter corr(wind, demand) anomalies"]):
        e = stats[stats.source == "ERA5"].set_index("country")[col]
        for r, m in zip("ABC", ["o", "s", "^"]):
            c = stats[stats.source == f"C2E-{r}"].set_index("country")[col]
            ax.scatter(e, c.reindex(e.index), marker=m, s=18, label=f"C2E {r}")
        lo, hi = np.nanmin([e.min(), stats[col].min()]), np.nanmax([e.max(), stats[col].max()])
        ax.plot([lo, hi], [lo, hi], "k--", lw=0.7)
        ax.set_xlabel("ERA5 (C3S)")
        ax.set_ylabel("Climate2Energy historical")
        ax.set_title(lab, fontsize=9)
    axes[0].legend(fontsize=8)
    fig.suptitle("ERA5 vs Climate2Energy historical, 1995-2014, 18 countries", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "wp1_era5_vs_c2e.png", dpi=150)


if __name__ == "__main__":
    main()
