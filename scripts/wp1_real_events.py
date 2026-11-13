"""WP1: real stressful events 2015-2025 and a weather-only stress index for today's fleet, tested on them.

1. Real events from market and system data:
   - price stress: daily mean day-ahead price at least 50% above its centred 31-day median (removes the gas-price
     level); a European price-stress day has >= 4 of 12 core bidding zones in price stress;
   - residual-load stress: observed load minus wind and solar, aggregated over the core countries, as an anomaly from
     its centred 365-day mean; top 3% of days.
2. Weather-only index: today's wind and PV fleet (2024 energy per country, observed) on ERA5 capacity factors
   (C3S, 1979-2026) and a temperature-driven daily demand model fitted on observed load 2015-2025 (frozen at 2024).
   No market data enter the index.
3. Test: correlation with observed residual load, hit rate and false-alarm ratio against the real event days,
   ranks and return periods of named events (January 2017 cold spell, November and December 2024 Dunkelflaute).
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stress import events as ev
from stress import obs
from stress import realdata as rd
from stress.paths import DERIVED, FIGURES, RESULTS

OUT = RESULTS / "wp1"
OUT.mkdir(parents=True, exist_ok=True)
PRICE_ZONES = ["DE", "FR", "NL", "BE", "AT", "CH", "PL", "CZ", "DK", "IT", "ES", "GB"]
STORYLINES = {"Jan 2017 cold spell": ("2017-01-16", "2017-01-26"),
              "Nov 2024 Dunkelflaute": ("2024-11-04", "2024-11-08"),
              "Dec 2024 Dunkelflaute": ("2024-12-10", "2024-12-14")}


def price_stress(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    d = prices[[c for c in PRICE_ZONES if c in prices]].resample("1D").mean()
    med = d.rolling(31, center=True, min_periods=15).median()
    ratio = d / med.where(med > 5)
    flags = ratio >= 1.5
    eu = flags.sum(axis=1) >= 4
    return ratio, eu


def main():
    # ---------------- observed panel
    panel = rd.observed_panel()
    load, wind, solar = panel["load"], panel["wind"], panel["solar"]
    cs = [c for c in rd.CORE if c in load and c in wind and c in solar]
    ld = load[cs].resample("1D").mean()
    wd = wind[cs].resample("1D").mean().fillna(0)
    sd = solar[cs].resample("1D").mean().fillna(0)
    ok = ld.notna().all(axis=1) & (ld.index >= "2015-01-01") & (ld.index < "2026-01-01")
    rl = (ld - wd - sd)[ok].sum(axis=1)
    rl_anom = (rl - rl.rolling(365, center=True, min_periods=180).mean()) / ld[ok].sum(axis=1).rolling(
        365, center=True, min_periods=180).mean()
    real_rl_days = rl_anom >= rl_anom.quantile(0.97)
    # ---------------- prices
    prices = obs.entsoe_panel("price")
    ratio, eu_price = price_stress(prices)
    # ---------------- today's fleet: 2024 energy (GW average) per country
    ref = slice("2024-01-01", "2024-12-31")
    cf_on, cf_off, cf_pv = obs.c3s("wind_on"), obs.c3s("wind_off"), obs.c3s("pv")
    en_on = obs.entsoe_panel("gen", "B19").loc[ref].mean() / 1000
    en_off = obs.entsoe_panel("gen", "B18").loc[ref].mean() / 1000
    en_pv = obs.entsoe_panel("gen", "B16").loc[ref].mean() / 1000
    energy = pd.DataFrame({"wind_on": en_on, "wind_off": en_off, "pv": en_pv}).fillna(0)
    energy = energy.loc[[c for c in energy.index if c in obs.C2E_COUNTRIES]]
    energy.to_csv(DERIVED / "current_fleet_energy.csv")
    clim = slice("1991-01-01", "2025-12-31")
    gen_w = pd.DataFrame(index=cf_on.resample("1D").mean().index)
    for tech, cf in [("wind_on", cf_on), ("wind_off", cf_off), ("pv", cf_pv)]:
        cfd = cf.resample("1D").mean()
        for c in cs:
            if c in cfd and energy.loc[c, tech] > 0:
                g = energy.loc[c, tech] * cfd[c] / cfd[c].loc[clim].mean()
                gen_w[c] = gen_w.get(c, 0) + g
    gen_w = gen_w.fillna(0)
    # ---------------- demand model per country
    t2m = obs.c3s("t2m").resample("1D").mean()
    dem_w, fit_rows = pd.DataFrame(index=t2m.index), []
    for c in cs:
        y = ld[c][ok]
        coef, r2, pred = rd.fit_daily_demand(y, t2m[c].reindex(y.index))
        dem_w[c] = pred(t2m.index, t2m[c].to_numpy())
        fit_rows.append({"country": c, "r2": r2, "hdd_GW_per_K": coef["hdd"], "cdd_GW_per_K": coef["cdd"]})
    pd.DataFrame(fit_rows).to_csv(OUT / "demand_model_fit.csv", index=False)
    index_w = (dem_w[cs] - gen_w[cs]).sum(axis=1).loc[:"2026-09-30"]
    index_w.to_frame("stress_index_GW").to_parquet(DERIVED / "era5_stress_index_daily.parquet")
    thr = index_w.quantile(0.97)
    pred_days = index_w >= thr
    # ---------------- skill on 2015-2025
    win = slice("2015-01-01", "2025-12-31")
    a = index_w.loc[win]
    a_anom = a - a.rolling(365, center=True, min_periods=180).mean()
    both = pd.concat({"index": a_anom, "obs": rl_anom * ld[ok].sum(axis=1)}, axis=1).dropna()
    skill = {"corr_index_vs_observed_residual_load_anomaly": both["index"].corr(both["obs"]),
             "spearman": both["index"].corr(both["obs"], method="spearman")}
    pred_win = pred_days.loc[win]
    h_rl = ev.hit_rate(pred_win, real_rl_days.reindex(pred_win.index, fill_value=False), 1)
    winter = pred_win.index.month.isin([10, 11, 12, 1, 2, 3])
    h_pr = ev.hit_rate(pred_win[winter], eu_price.reindex(pred_win.index, fill_value=False)[winter], 1)
    # climatological baseline: random days with the same frequency in winter
    rng = np.random.default_rng(0)
    base = []
    for _ in range(200):
        rnd = pd.Series(rng.random(len(pred_win)) < pred_win[winter].mean(), pred_win.index)[winter]
        base.append(ev.hit_rate(rnd, eu_price.reindex(pred_win.index, fill_value=False)[winter], 1)["hit_rate"])
    # price ratio vs index (winter days)
    pr_eu = ratio.reindex(a.index).median(axis=1)
    m = winter & pr_eu.notna().to_numpy()
    skill.update({"index_vs_rl_days": h_rl, "index_vs_eu_price_days_winter": h_pr,
                  "random_hit_rate_price_winter_mean": float(np.mean(base)),
                  "random_hit_rate_price_winter_p95": float(np.quantile(base, 0.95)),
                  "spearman_index_vs_median_price_ratio_winter": a_anom[m].corr(pr_eu[m], method="spearman")})
    pd.Series({k: (v if not isinstance(v, dict) else str({kk: round(vv, 3) for kk, vv in v.items()}))
               for k, v in skill.items()}).to_csv(OUT / "stress_index_skill.csv", header=["value"])
    # ---------------- storylines: rank and return period in 1979-2025 for today's fleet (3-day mean index)
    full = index_w.loc["1979-01-01":"2025-12-31"]
    roll = full.rolling(3, center=True).mean()
    ann_max = roll.groupby(roll.index.year).max()
    rows = []
    for name, (s, e) in STORYLINES.items():
        v = roll.loc[s:e].max()
        day = roll.loc[s:e].idxmax()
        rows.append({"event": name, "peak_3day_index_GW": v, "date": day.date(),
                     "years_reaching_it_1979_2025": int((ann_max >= v).sum()),
                     "empirical_return_period_y": ev.empirical_return_period(ann_max.to_numpy(), v, len(ann_max)),
                     "rank_among_annual_maxima": int((ann_max > v).sum()) + 1,
                     "obs_rl_anomaly_pct": 100 * rl_anom.loc[s:e].max(),
                     "eu_price_days": int(eu_price.loc[s:e].sum()),
                     "de_max_price_ratio": float(ratio["DE"].loc[s:e].max()) if "DE" in ratio else np.nan})
    story = pd.DataFrame(rows)
    story.to_csv(OUT / "storylines.csv", index=False)
    # ---------------- event catalogue 2015-2025 (index events merged over 1-day gaps)
    cat = ev.exceedance_events(index_w.loc[win], thr, merge_gap=1)
    cat["obs_rl_days"] = [int(real_rl_days.loc[s:e].sum()) for s, e in zip(cat.start, cat.end)]
    cat["eu_price_days"] = [int(eu_price.loc[s:e].sum()) for s, e in zip(cat.start, cat.end)]
    cat.drop(columns=["i0", "i1"]).to_csv(OUT / "event_catalogue_2015_2025.csv", index=False)
    print(pd.DataFrame(fit_rows).round(3).to_string())
    print(skill)
    print(story.round(2).to_string())
    print(cat.drop(columns=["i0", "i1"]).round(1).to_string())
    plot(index_w, thr, rl_anom, eu_price)


def plot(index_w, thr, rl_anom, eu_price):
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    w = index_w.loc["2015":"2025"]
    axes[0].plot(w.index, w, lw=0.5, color="0.3")
    axes[0].axhline(thr, color="tab:red", lw=0.8, label="top 3% of 1979-2026")
    axes[0].set_ylabel("weather-only stress\nindex (GW)")
    axes[0].legend(fontsize=8, loc="upper right")
    axes[1].plot(rl_anom.index, 100 * rl_anom, lw=0.5, color="tab:blue")
    axes[1].set_ylabel("observed residual load\nanomaly (% of load)")
    e = eu_price.astype(int).rolling(1).max()
    axes[2].bar(e.index, e, width=1.0, color="tab:orange")
    axes[2].set_ylabel("European\nprice-stress day")
    for ax in axes:
        for s, en in STORYLINES.values():
            ax.axvspan(pd.Timestamp(s), pd.Timestamp(en), color="tab:red", alpha=0.15)
    fig.suptitle("Today's fleet on 2015-2025 weather vs observed system and prices (shaded: named events)", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "wp1_real_events.png", dpi=150)


if __name__ == "__main__":
    main()
