"""WP3 by country: stressful periods and Dunkelflaute, present (1995-2014) vs SSP3-7.0 (2080-2099), 3 realizations.

Balanced net-zero fleet (60% wind / 40% PV energy, VRE = 80% of demand), current heating electrification.
- net-load stress hours: country net load above its own 98th percentile (joint over both periods and realizations);
- Dunkelflaute: days whose VRE output is below the country's present-day 3rd percentile, in spells of >= 2 days;
- 20-year return level of the longest spell (GPD on spell lengths);
- signal-to-noise: future minus present (mean over realizations) divided by the standard deviation of the 20-year
  statistic from a block bootstrap over years (internal variability within one realization) and across realizations.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stress import events as ev
from stress import system as sy
from stress.paths import FIGURES, RESULTS
from stress.pipeline import PERIODS, REALS, compute_netload, demand_from, load_inputs

OUT = RESULTS / "wp3"
RNG = np.random.default_rng(42)


def boot_sd(per_year: pd.Series, n=500):
    v = per_year.to_numpy()
    return np.std([RNG.choice(v, len(v)).mean() for _ in range(n)])


def main():
    profile, cs, data = load_inputs()
    has_off = set(data[("A", "historical")]["cf"]["wind_off"].columns)
    ann = demand_from(data[("A", "historical")], profile, "heat").mean()
    fleets = sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), has_off)
    fl = {"balanced": fleets["balanced"]}
    nl = compute_netload(profile, cs, data, fl, "heat")
    thr = pd.concat([nl[("balanced", r, p)] for r in REALS for p in PERIODS]).quantile(0.98)
    # Dunkelflaute threshold: 3rd percentile of present-day daily VRE output (pooled over realizations), per country
    daily_norm = {}
    for r in REALS:
        ref = {t: data[(r, "historical")]["cf"][t].mean() for t in sy.VRE}
        for p in PERIODS:
            g = sy.generation(fl["balanced"], data[(r, p)]["cf"], ref)
            gref = sy.generation(fl["balanced"], data[(r, "historical")]["cf"], ref).mean()
            daily_norm[(r, p)] = g.resample("1D").mean() / gref
    dthr = pd.concat([daily_norm[(r, "historical")] for r in REALS]).quantile(0.03)
    rows = []
    for r in REALS:
        ref = {t: data[(r, "historical")]["cf"][t].mean() for t in sy.VRE}
        for p in PERIODS:
            n = nl[("balanced", r, p)]
            gd = daily_norm[(r, p)]
            for c in cs:
                if c not in gd or not np.isfinite(dthr.get(c, np.nan)):
                    continue
                stress = n[c] > thr[c]
                per_year_stress = stress.groupby(stress.index.year).sum()
                per_year_stress = per_year_stress[per_year_stress.index.map(lambda y: (n.index.year == y).sum() > 8000)]
                df_low = ev.low_events(gd[c], dthr[c], min_len=2)
                flags = ev.daily_flags(df_low, gd.index)
                low_year = flags.groupby(flags.index.year).sum()
                low_year = low_year[low_year.index.isin(per_year_stress.index)]
                rows.append({"country": c, "real": r, "period": p,
                             "stress_h_per_year": per_year_stress.mean(), "stress_h_boot_sd": boot_sd(per_year_stress),
                             "dunkel_days_per_year": low_year.mean(), "dunkel_boot_sd": boot_sd(low_year),
                             "dunkel_spells_per_year": len(df_low) / len(low_year),
                             "dunkel_max_len_d": df_low.duration.max() if len(df_low) else 0,
                             "dunkel_djf_share": float(flags[flags.index.month.isin([11, 12, 1, 2])].sum() / max(flags.sum(), 1)),
                             "dunkel_rl20_len_d": ev.gpd_return_levels(df_low.duration.to_numpy(), len(low_year),
                                                                       periods=(20,), q=0.5).iloc[0]})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "country_stats.csv", index=False)
    dthr.rename("dunkel_threshold_rel_to_mean").to_csv(OUT / "dunkel_thresholds.csv")
    # change and signal-to-noise
    out = []
    for c, sub in df.groupby("country"):
        h, f = sub[sub.period == "historical"], sub[sub.period == "SSP370"]
        for var, sdcol in [("stress_h_per_year", "stress_h_boot_sd"), ("dunkel_days_per_year", "dunkel_boot_sd")]:
            d = f[var].mean() - h[var].mean()
            # noise: sampling sd of a 20-year mean (block bootstrap over years) in both periods + spread across
            # realizations of the present-day mean (multi-decadal internal variability)
            noise = np.sqrt(np.mean(h[sdcol] ** 2) + np.mean(f[sdcol] ** 2) + np.var(h[var], ddof=1))
            per_real = (f.set_index("real")[var] - h.set_index("real")[var])
            out.append({"country": c, "variable": var, "historical": h[var].mean(), "SSP370": f[var].mean(),
                        "change": d, "change_pct": 100 * d / h[var].mean() if h[var].mean() else np.nan,
                        "real_change_min": per_real.min(), "real_change_max": per_real.max(),
                        "same_sign_all_reals": bool((np.sign(per_real) == np.sign(d)).all()),
                        "signal_to_noise": d / noise if noise > 0 else np.nan})
    ch = pd.DataFrame(out)
    ch.to_csv(OUT / "country_change.csv", index=False)
    print(ch.round(2).to_string())
    plot(ch)


def plot(ch):
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    for ax, var, lab in zip(axes, ["stress_h_per_year", "dunkel_days_per_year"],
                            ["net-load stress hours per year\n(> country P98)", "Dunkelflaute days per year\n(VRE < present P3, >= 2 d)"]):
        s = ch[ch.variable == var].set_index("country").sort_index()
        x = np.arange(len(s))
        col = ["tab:red" if (abs(v) >= 2 and a) else "0.6" for v, a in zip(s.signal_to_noise, s.same_sign_all_reals)]
        ax.bar(x, s.change, color=col)
        ax.errorbar(x, s.change, yerr=[s.change - s.real_change_min, s.real_change_max - s.change], fmt="none",
                    ecolor="k", lw=0.7)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylabel(lab, fontsize=9)
        ax.set_xticks(x, s.index, fontsize=8)
    axes[0].set_title("Change 2080-2099 (SSP3-7.0) vs 1995-2014, balanced net-zero fleet; red: |signal/noise| >= 2 and "
                      "same sign in all 3 realizations; whiskers: realization range", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES / "wp3_country_change.png", dpi=150)


if __name__ == "__main__":
    main()
