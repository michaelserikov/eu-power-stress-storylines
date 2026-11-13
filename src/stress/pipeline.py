"""Shared pipeline: Climate2Energy inputs, demand and net load per fleet, realization and period."""
from __future__ import annotations

import pandas as pd

from . import system as sy

REALS = ["A", "B", "C"]
PERIODS = ["historical", "SSP370"]
SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM", 6: "JJA", 7: "JJA", 8: "JJA",
          9: "SON", 10: "SON", 11: "SON"}


def load_inputs():
    profile = sy.baseline_profile([c for c in sy.obs.C2E_COUNTRIES])
    cs = list(profile.columns)
    data = {}
    for r in REALS:
        for p in PERIODS:
            cf = {t: sy.c2e_frame(t, r, p) for t in sy.VRE}
            data[(r, p)] = {"cf": cf, "ror": sy.c2e_frame("ror", r, p),
                            "heat": sy.c2e_frame("heat", r, p)[cs], "heat_full": sy.c2e_frame("heat_full", r, p)[cs],
                            "cool": sy.c2e_frame("cool", r, p)[cs]}
    return profile, cs, data


def demand_from(data_rp, profile, heat_key, cool_factor=1.0, extra=None):
    idx = data_rp[heat_key].index
    base = sy.expand_baseline(profile, idx)
    d = base + data_rp[heat_key] + cool_factor * data_rp["cool"].reindex(idx).fillna(0)
    if extra is not None:
        d = d + extra(idx, list(d.columns))
    return d


def compute_netload(profile, cs, data, fleets, heat_key, cool_factor=1.0, extra=None):
    """Return {(fleet, r, p): country net load frame}."""
    out = {}
    for r in REALS:
        ref = {t: data[(r, "historical")]["cf"][t].mean() for t in sy.VRE}
        for p in PERIODS:
            d = demand_from(data[(r, p)], profile, heat_key, cool_factor, extra)
            for fname, fl in fleets.items():
                g = sy.generation(fl, data[(r, p)]["cf"], ref)
                out[(fname, r, p)] = sy.net_load(d, g, data[(r, p)]["ror"]).astype("float32")
    return out


