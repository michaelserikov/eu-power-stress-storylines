"""WP3 robustness: does the result depend on which realization calibrated the bias correction?

Climate2Energy ships every realization (Y) corrected with the quantile maps of every realization (X). The headline
statistic (change in hours of European net load above P90, high-wind fleet, current heating) is recomputed for all
nine X-Y combinations and split into the spread due to the realization and the spread due to the calibration member.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from stress import c2e, obs
from stress import system as sy
from stress.paths import RESULTS
from stress.pipeline import PERIODS

OUT = RESULTS / "wp3"
VARS = ["pv", "wind_on", "wind_off", "heat", "cool", "ror"]


def frame(v, bc, r, p):
    df = c2e.load(v, r, p, bc=bc).rename(columns=obs.NAME_TO_ISO)
    if v == "ror":
        idx = pd.date_range(df.index.min(), df.index.max() + pd.Timedelta("23h"), freq="1h")
        df = (df / 24.0).reindex(idx, method="ffill")
    return df


def main():
    profile = sy.baseline_profile(obs.C2E_COUNTRIES)
    cs = list(profile.columns)
    ref_d = {}
    rows = []
    eu = {}
    for bc in "ABC":
        for r in "ABC":
            data = {p: {v: frame(v, bc, r, p) for v in VARS} for p in PERIODS}
            if not ref_d:
                d0 = sy.expand_baseline(profile, data["historical"]["heat"].index) + data["historical"]["heat"][cs] + \
                    data["historical"]["cool"][cs]
                ref_d["ann"] = d0.mean()
                off = set(data["historical"]["wind_off"].columns)
                ref_d["fleet"] = sy.scenario_fleets(ref_d["ann"], pd.DataFrame(0, index=ref_d["ann"].index,
                                                                                 columns=list(sy.VRE)), off)["high_wind"]
            ref = {t: data["historical"][t].mean() for t in sy.VRE}
            for p in PERIODS:
                x = data[p]
                d = sy.expand_baseline(profile, x["heat"].index) + x["heat"][cs] + x["cool"][cs].reindex(x["heat"].index).fillna(0)
                g = sy.generation(ref_d["fleet"], {t: x[t] for t in sy.VRE}, ref)
                eu[(bc, r, p)] = sy.net_load(d, g, x["ror"]).sum(axis=1)
            print(bc, r, flush=True)
    thr = pd.concat(eu.values()).quantile(0.90)
    for bc in "ABC":
        for r in "ABC":
            h = (eu[(bc, r, "historical")] > thr).mean()
            f = (eu[(bc, r, "SSP370")] > thr).mean()
            rows.append({"bias_correction_member": bc, "realization": r, "change_pct": 100 * (f / h - 1)})
    df = pd.DataFrame(rows)
    piv = df.pivot(index="realization", columns="bias_correction_member", values="change_pct")
    piv.to_csv(OUT / "bc_member_sensitivity.csv")
    spread = {"range_all_9": float(df.change_pct.max() - df.change_pct.min()),
              "mean_range_across_realizations_same_bc": float((piv.max(axis=0) - piv.min(axis=0)).mean()),
              "mean_range_across_bc_same_realization": float((piv.max(axis=1) - piv.min(axis=1)).mean()),
              "diagonal_mean": float(np.mean(np.diag(piv.to_numpy()))), "all_mean": float(df.change_pct.mean())}
    pd.Series(spread).to_csv(OUT / "bc_member_spread.csv", header=["value"])
    print(piv.round(1))
    print(spread)


if __name__ == "__main__":
    main()
