"""WP4: technological trends and their contribution to future stressful periods, against the climate contribution.

Technology settings (illustrative scenarios built on open sources, not projections):
- air conditioning: Climate2Energy cooling demand x 1 (today), x 2 and x 3. IEA, The Future of Cooling (2018),
  projects the global stock of air conditioners to grow roughly threefold by 2050; Europe is used here with the same
  multipliers as a range, not as a European projection;
- heat pumps: share f of the gap between today's electric heating and the fully electrified case of Climate2Energy,
  f = 0 (today), 0.5 and 1;
- electric vehicles: a fully electrified car fleet at about 450 TWh a year for the 29 countries (order of magnitude of
  about 2.5 trillion vehicle-km at 0.18 kWh/km, in line with JRC and EEA fleet statistics), split by today's demand,
  with a cold-weather penalty of up to +25% (battery heating; driven by the C2E heating signal) and two charging
  profiles: uncontrolled (evening peak) and smart (night valley).
Fleet: balanced net-zero VRE (60% wind / 40% PV) sized to 80% of each case's annual demand.
Metric: hours and energy per year above a fixed level (the 98th percentile of European net load today with today's
technology, i.e. today's firm capacity), and the 99.9th percentile of net load.
Decomposition (2x2 factorial per technology case): climate effect = future minus present weather with today's
technology, technology effect = new minus today's technology in present weather, interaction = the rest (how the
climate signal changes once the technology is there).
Heat pumps: C2E's fully electrified heating is read as resistive-equivalent (an assumption) and divided by a COP that
falls from 3.5 in mild hours to 2.0 at the cold peak (cold = heating demand relative to its 99th percentile).
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from stress import system as sy
from stress.paths import FIGURES, RESULTS
from stress.pipeline import PERIODS, REALS, demand_from, load_inputs

OUT = RESULTS / "wp4"
OUT.mkdir(parents=True, exist_ok=True)
EV_TWH = 450.0
UNCONTROLLED = np.array([2, 1.5, 1, 1, 1, 1.5, 2.5, 3, 3, 3, 3, 3.5, 3.5, 3.5, 4, 5, 6.5, 8, 9, 9, 7.5, 6, 4.5, 3])
SMART = np.array([8, 9, 9, 9, 8, 6, 4, 2.5, 2, 2, 2.5, 3, 3, 3, 3, 3, 2.5, 2, 2, 2.5, 3, 4, 5.5, 7])


def ev_demand(heat: pd.DataFrame, share: pd.Series, profile: np.ndarray) -> pd.DataFrame:
    """Hourly EV charging, GW: EV_TWH split by share, hourly profile, +25% at the coldest heating level."""
    prof = profile / profile.mean()
    base = (EV_TWH * 1000 / 8760) * share  # GW average per country
    h = heat[share.index]
    cold = (h / h.quantile(0.99)).clip(0, 1)
    factor = (1 + 0.25 * cold)
    factor = factor / factor.mean()
    return factor.mul(base, axis=1).mul(prof[h.index.hour], axis=0)


def case_demand(d_rp, profile, f_hp, ac, ev, cop=False):
    full = d_rp["heat_full"]
    if cop:  # heat pumps: C2E full electrification (read as resistive-equivalent) / COP, 3.5 mild to 2.0 at the cold peak
        cold = (d_rp["heat"] / d_rp["heat"].quantile(0.99)).clip(0, 1)
        full = full / (3.5 - 1.5 * cold)
    heat = d_rp["heat"] + f_hp * (full - d_rp["heat"]).clip(lower=0)
    idx = heat.index
    dem = sy.expand_baseline(profile, idx) + heat + ac * d_rp["cool"].reindex(idx).fillna(0)
    if ev is not None:
        share = profile.mean() / profile.mean().sum()
        dem = dem + ev_demand(d_rp["heat"], share, ev)
    return dem


CASES = {"today": (0.0, 1, None, False), "AC x2": (0.0, 2, None, False), "AC x3": (0.0, 3, None, False),
         "electric heating 50% (C2E scaling)": (0.5, 1, None, False),
         "electric heating 100% (C2E scaling)": (1.0, 1, None, False),
         "heat pumps 50%": (0.5, 1, None, True), "heat pumps 100%": (1.0, 1, None, True),
         "EV uncontrolled": (0.0, 1, UNCONTROLLED, False), "EV smart": (0.0, 1, SMART, False),
         "combined (HP 50%, AC x2, EV smart)": (0.5, 2, SMART, True),
         "combined (HP 50%, AC x2, EV uncontrolled)": (0.5, 2, UNCONTROLLED, True)}


def main():
    profile, cs, data = load_inputs()
    has_off = set(data[("A", "historical")]["cf"]["wind_off"].columns)
    eu = {}
    for case, (f, ac, evp, cop) in CASES.items():
        ann = case_demand(data[("A", "historical")], profile, f, ac, evp, cop).mean()
        fl = sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), has_off)["balanced"]
        for r in REALS:
            ref = {t: data[(r, "historical")]["cf"][t].mean() for t in sy.VRE}
            for p in PERIODS:
                d = case_demand(data[(r, p)], profile, f, ac, evp, cop)
                g = sy.generation(fl, data[(r, p)]["cf"], ref)
                eu[(case, r, p)] = sy.net_load(d, g, data[(r, p)]["ror"]).sum(axis=1)
    level = pd.concat([eu[("today", r, "historical")] for r in REALS]).quantile(0.98)
    rows = []
    for (case, r, p), x in eu.items():
        yrs = len(x) / 8760
        ex = (x - level).clip(lower=0)
        summer = x.index.month.isin([6, 7, 8])
        rows.append({"case": case, "real": r, "period": p, "hours_above_today_p98": (x > level).sum() / yrs,
                     "energy_above_TWh": ex.sum() / yrs / 1000, "summer_hours_above": (x[summer] > level).sum() / yrs,
                     "p99_9_GW": x.quantile(0.999), "mean_GW": x.mean()})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "technology_cases.csv", index=False)
    m = df.groupby(["case", "period"]).mean(numeric_only=True)
    dec = []
    for case in CASES:
        if case == "today":
            continue
        for metric in ["hours_above_today_p98", "energy_above_TWh", "p99_9_GW", "summer_hours_above"]:
            a = m.loc[("today", "historical"), metric]
            b = m.loc[("today", "SSP370"), metric]
            c = m.loc[(case, "historical"), metric]
            d = m.loc[(case, "SSP370"), metric]
            climate = b - a  # future weather, today's technology
            tech = c - a     # today's weather, new technology
            dec.append({"case": case, "metric": metric, "today_present": a, "total_change": d - a,
                        "climate_effect": climate, "technology_effect": tech, "interaction": (d - a) - climate - tech})
    dec = pd.DataFrame(dec)
    dec.to_csv(OUT / "decomposition.csv", index=False)
    print(m.round(1).to_string())
    print(dec.round(1).to_string())
    plot(dec)


def plot(dec):
    s = dec[dec.metric == "hours_above_today_p98"].set_index("case")
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(s))
    ax.bar(x - 0.25, s.climate_effect, 0.25, label="climate (SSP3-7.0 2080-2099 vs 1995-2014)")
    ax.bar(x, s.technology_effect, 0.25, label="technology")
    ax.bar(x + 0.25, s.interaction, 0.25, label="interaction")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xticks(x, s.index, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("hours per year above today's P98\n(European net load)")
    ax.legend(fontsize=8)
    ax.set_title("Climate vs technology contribution to stressful hours, mean of 3 realizations", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "wp4_decomposition.png", dpi=150)


if __name__ == "__main__":
    main()
