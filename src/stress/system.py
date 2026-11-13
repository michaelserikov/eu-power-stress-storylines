"""Power-system layer: demand, renewable fleets and net load on a fixed system.

Net load follows Bloin-Wibe et al. (2026, ERL): N(t) = D(t) - G(t), with D = weather-insensitive baseline + electric
heating + cooling (Climate2Energy, demand.ninja) and G = onshore and offshore wind + PV + run-of-river. Reservoir hydro
is treated as a flexibility option (WP5), not in N. Fleets are defined by annual energy: each technology's capacity
is set so that its long-run mean output in the reference climate (historical period of the same realization, or the
whole ERA5 record) equals a target energy, so turbine-model level differences between datasets cancel while the
time structure and the climate change signal pass through.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import c2e, obs

VRE = ("wind_on", "wind_off", "pv")


def c2e_frame(variable: str, real: str, period: str) -> pd.DataFrame:
    df = c2e.load(variable, real, period).rename(columns=obs.NAME_TO_ISO)
    if variable in ("ror",):  # daily GWh -> hourly GW, flat within the day
        hourly_idx = pd.date_range(df.index.min(), df.index.max() + pd.Timedelta("23h"), freq="1h")
        df = (df / 24.0).reindex(hourly_idx, method="ffill")
    return df


@dataclass
class Fleet:
    """Annual mean output targets in GW (average power) per country and technology."""
    name: str
    energy: pd.DataFrame  # index country, columns wind_on, wind_off, pv (GW average)
    note: str = ""


@dataclass
class Demand:
    name: str
    heat: str = "heat"          # "heat" (current electrification) or "heat_full"
    cool_factor: float = 1.0    # multiplier on C2E cooling demand (air-conditioning adoption, WP4)
    extra: dict = field(default_factory=dict)  # name -> callable(index, countries) -> frame (GW), e.g. EV charging


# ------------------------------------------------------------------ baseline demand
def baseline_profile(countries: list[str]) -> pd.DataFrame:
    """Weather-insensitive demand by (month, weekday flag, hour), GW: OPSD 2015-2019 observed load climatology minus
    the Climate2Energy historical (realization A) heating + cooling climatology for the same calendar keys."""
    load = obs.opsd("load")["2015":"2019"]
    load = load[[c for c in countries if c in load]] / 1000.0
    heat = c2e_frame("heat", "A", "historical")
    cool = c2e_frame("cool", "A", "historical")
    wsens = (heat + cool.reindex(heat.index).fillna(0))[load.columns]

    def keys(ix):
        return [ix.month, (ix.dayofweek >= 5).astype(int), ix.hour]

    lc = load.groupby(keys(load.index)).mean()
    wc = wsens.groupby([wsens.index.month, wsens.index.hour]).mean()
    base = lc.copy()
    for (m, w, h) in lc.index:
        base.loc[(m, w, h)] = lc.loc[(m, w, h)] - wc.loc[(m, h)]
    floor = 0.3 * lc.mean()
    return base.clip(lower=floor, axis=1)


def expand_baseline(profile: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    k = pd.MultiIndex.from_arrays([index.month, (index.dayofweek >= 5).astype(int), index.hour])
    out = profile.reindex(k)
    out.index = index
    return out


def demand(d: Demand, real: str, period: str, profile: pd.DataFrame) -> pd.DataFrame:
    heat = c2e_frame(d.heat, real, period)
    idx = heat.index
    cs = list(profile.columns)
    cool = c2e_frame("cool", real, period).reindex(idx).fillna(0)
    out = expand_baseline(profile, idx)[cs] + heat[cs] + d.cool_factor * cool[cs]
    for f in d.extra.values():
        out = out + f(idx, cs)
    return out


# ------------------------------------------------------------------ fleets
def generation(fleet: Fleet, cf: dict[str, pd.DataFrame], cf_ref_mean: dict[str, pd.Series]) -> pd.DataFrame:
    """Hourly VRE generation, GW: energy target * cf / mean(cf in reference climate)."""
    total = None
    for tech in VRE:
        if tech not in cf:
            continue
        e = fleet.energy[tech].reindex(cf[tech].columns).fillna(0)
        g = cf[tech].mul(e / cf_ref_mean[tech].replace(0, np.nan), axis=1).fillna(0)
        total = g if total is None else total.add(g, fill_value=0)
    return total


def scenario_fleets(annual_demand: pd.Series, current: pd.DataFrame, has_offshore: set[str]) -> dict[str, Fleet]:
    """Current fleet (observed energy shares) and three stylised net-zero variants with VRE energy equal to 80% of each
    country's annual demand: balanced (60% wind / 40% PV), high wind (80/20), high solar (30/70). Offshore takes 40%
    of the wind energy where C2E has offshore output. Illustrative, not TYNDP capacities."""
    fleets = {"current": Fleet("current", current.reindex(annual_demand.index).fillna(0),
                               "observed wind and PV energy per country")}
    for name, w in {"balanced": 0.6, "high_wind": 0.8, "high_solar": 0.3}.items():
        vre = 0.8 * annual_demand
        off_share = pd.Series([0.4 if c in has_offshore else 0.0 for c in annual_demand.index], annual_demand.index)
        e = pd.DataFrame({"wind_on": vre * w * (1 - off_share), "wind_off": vre * w * off_share, "pv": vre * (1 - w)})
        fleets[name] = Fleet(name, e, f"VRE = 80% of annual demand, wind share {w:.0%}")
    return fleets


# ------------------------------------------------------------------ net load
def net_load(dem: pd.DataFrame, gen: pd.DataFrame, ror: pd.DataFrame | None = None) -> pd.DataFrame:
    cs = dem.columns
    n = dem - gen.reindex(columns=cs).fillna(0).reindex(dem.index)
    if ror is not None:
        n = n - ror.reindex(columns=cs).fillna(0).reindex(dem.index).fillna(0)
    return n
