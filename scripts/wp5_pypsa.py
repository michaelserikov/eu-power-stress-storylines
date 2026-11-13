"""WP5b: capacity expansion sized on a stressful year vs a normal year, present vs SSP3-7.0, in PyPSA.

Model: the greenfield-renewables country model of northwestern Europe (12 countries, transport model with AC and HVDC
limits, existing nuclear and hydro, extendable wind, PV, batteries, hydrogen storage and backup, load shedding at
8000 EUR/MWh) from github.com/michaelserikov/eu-weather-years-pypsa (same author), imported from its source folder
(WEATHERYEARS_SRC). Here it is driven by Climate2Energy weather instead of renewables.ninja: C2E wind (onshore,
offshore) and PV capacity factors, and demand = baseline + C2E heating + cooling (current electrification).
For realization A (B and C with WP5_REALS=ABC) and both periods: the stress year (highest 7-day mean net load of the 12 countries for a
balanced fleet) and a normal year (median of the annual 7-day maxima). Each design is then operated with fixed
capacities on the other designs' years: lost load and backup energy show what a design misses.
6-hour steps (the source repo checked 6 h against 3 h). Costs: PyPSA technology-data 2030 as in the source repo. Illustrative system, not a plan.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.environ.get("WEATHERYEARS_SRC", str(Path.home() / "eu-weather-years-pypsa" / "src")))
from weatheryears import inputs, model  # noqa: E402

from stress import system as sy  # noqa: E402
from stress.paths import RESULTS  # noqa: E402
from stress.pipeline import PERIODS, compute_netload, demand_from, load_inputs  # noqa: E402

OUT = RESULTS / "wp5"
ZONES = inputs.ZONES
STEP = int(os.environ.get("WP5_STEP", 6))


def year_frames(data_rp, profile, year):
    cf = {}
    for z in ZONES:
        cf[f"{z}_pv_national_current"] = data_rp["cf"]["pv"][z]
        cf[f"{z}_wind_onshore_current"] = data_rp["cf"]["wind_on"][z]
        if z in data_rp["cf"]["wind_off"] and z in inputs.OFFSHORE_GW:
            cf[f"{z}_wind_offshore_current"] = data_rp["cf"]["wind_off"][z]
    cf = pd.DataFrame(cf)
    dem = demand_from(data_rp, profile, "heat")[ZONES] * 1000.0  # MW
    # C2E stamps are hour-ending; shift to hour-beginning and keep one calendar year
    cf.index = cf.index - pd.Timedelta("1h")
    dem.index = dem.index - pd.Timedelta("1h")
    w = model.weather_year(cf, year, STEP)
    d = inputs.no_leap(dem[dem.index.year == year])
    return w, d


def pick_years(eu: pd.Series):
    w7 = eu.rolling(168).mean()
    am = w7.groupby(w7.index.year).max()
    am = am[[y for y in am.index if (eu.index.year == y).sum() >= 8700]]
    stress = int(am.idxmax())
    normal = int((am - am.median()).abs().idxmin())
    return stress, normal, am


def main():
    profile, cs, data = load_inputs()
    has_off = set(data[("A", "historical")]["cf"]["wind_off"].columns)
    ann = demand_from(data[("A", "historical")], profile, "heat").mean()
    fl = {"balanced": sy.scenario_fleets(ann, pd.DataFrame(0, index=ann.index, columns=list(sy.VRE)), has_off)["balanced"]}
    nl = compute_netload(profile, cs, data, fl, "heat")
    costs = inputs.load_costs()
    limits = inputs.transfer_limits()
    existing = inputs.existing_fleet()
    designs, rows = {}, []
    reals = os.environ.get("WP5_REALS", "A")  # about 30 min per design on a laptop; ABC for all realizations
    for r in reals:
        for p in PERIODS:
            eu = nl[("balanced", r, p)][ZONES].sum(axis=1)
            stress, normal, am = pick_years(eu)
            for kind, y in [("stress", stress), ("normal", normal)]:
                w, d = year_frames(data[(r, p)], profile, y)
                t0 = time.time()
                n = model.build(w, d, costs, limits, existing, zones=ZONES, step=STEP)
                model.solve(n)
                fleet = model.fleet_of(n)
                designs[(r, p, kind)] = (fleet, w, d)
                cap = pd.Series(fleet)
                rows.append({"real": r, "period": p, "design_year_kind": kind, "year": y,
                             "max_7day_netload_GW": am.loc[y] / 1.0, "cost_bn_per_year": n.objective / 1e9,
                             "onwind_GW": cap[cap.index.str.endswith("onwind")].sum() / 1000,
                             "offwind_GW": cap[cap.index.str.endswith("offwind")].sum() / 1000,
                             "solar_GW": cap[cap.index.str.endswith("solar")].sum() / 1000,
                             "battery_GWh": cap[cap.index.str.endswith("battery store")].sum() / 1000,
                             "h2_store_TWh": cap[cap.index.str.endswith("H2 store")].sum() / 1e6,
                             "backup_GW": cap[cap.index.str.endswith("backup")].sum() / 1000,
                             "solve_s": time.time() - t0})
                print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(OUT / "pypsa_designs.csv", index=False)
    # cross-operation: each design on every other year (fixed capacities)
    cross = []
    pairs = []
    for r in reals:
        for p in PERIODS:
            pairs.append(((r, p, "normal"), (r, p, "stress")))  # a normal-year design meets the stress year
        pairs.append(((r, "historical", "stress"), (r, "SSP370", "stress")))  # today's design meets a future stress year
        pairs.append(((r, "SSP370", "stress"), (r, "historical", "stress")))
    for kd, kw in pairs:
        fleet = designs[kd][0]
        if True:
            _, w, d = designs[kw]
            n = model.build(w, d, costs, limits, existing, zones=ZONES, fleet=fleet, step=STEP)
            model.solve(n)
            shed = n.generators_t.p.filter(like=" shed").sum().sum() * STEP
            backup = n.generators_t.p.filter(like=" backup").sum().sum() * STEP
            cross.append({"design": "_".join(kd), "operated_on": "_".join(kw), "lost_load_GWh": shed / 1000,
                          "backup_TWh": backup / 1e6, "operating_cost_bn": n.objective / 1e9})
    cr = pd.DataFrame(cross)
    cr.to_csv(OUT / "pypsa_cross_operation.csv", index=False)
    print(cr.round(2).to_string())


if __name__ == "__main__":
    main()
