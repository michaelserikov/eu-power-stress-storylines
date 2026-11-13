"""WP1: observed system 2015-2025 and a weather-only stress index for today's fleet on ERA5.

Observed panel: OPSD (2015 to 2020-09) and ENTSO-E (2020-10 to 2025) load, wind and solar per country; ENTSO-E
day-ahead prices 2015-2025. Weather-only index: C3S ERA5-based capacity factors 1979-2026 x today's fleet (energy
shares observed in the calibration year) and a temperature-driven daily demand model fitted on observed load.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import obs

# GB is left out: ENTSO-E stopped publishing GB data after Brexit, so 2021-2025 would be missing
CORE = ["AT", "BE", "CH", "CZ", "DE", "DK", "ES", "FI", "FR", "IE", "IT", "NL", "NO", "PL", "PT", "SE"]


def _combine(op: pd.DataFrame, en: pd.DataFrame, switch="2020-10-01") -> pd.DataFrame:
    a = op[op.index < switch]
    b = en[en.index >= switch]
    return pd.concat([a, b]).sort_index()


def observed_panel() -> dict[str, pd.DataFrame]:
    """Hourly observed load, wind (on+off) and solar in GW, 2015-2025."""
    en_load = obs.entsoe_panel("load") / 1000
    en_on = obs.entsoe_panel("gen", "B19") / 1000
    en_off = obs.entsoe_panel("gen", "B18") / 1000
    en_pv = obs.entsoe_panel("gen", "B16") / 1000
    op = {k: obs.opsd(k) / 1000 for k in ("load", "wind_on", "wind_off", "wind", "solar")}
    op_wind = op["wind"].combine_first(op["wind_on"].add(op["wind_off"], fill_value=0))
    en_wind = en_on.add(en_off, fill_value=0)
    out = {"load": _combine(op["load"], en_load), "wind": _combine(op_wind, en_wind),
           "solar": _combine(op["solar"], en_pv)}
    return {k: v[[c for c in v.columns if c in obs.C2E_COUNTRIES]] for k, v in out.items()}


def prices() -> pd.DataFrame:
    p = obs.entsoe_panel("price")
    return p


# ------------------------------------------------------------------ demand model
def fit_daily_demand(load_daily: pd.Series, t_daily: pd.Series, heat_base=15.5, cool_base=22.0):
    """OLS of daily mean load on HDD, CDD, weekday dummies, holiday-season dummy and a linear trend.
    Returns (coefficients, predict function)."""
    df = pd.concat({"y": load_daily, "t": t_daily}, axis=1).dropna()

    def design(ix, t):
        X = pd.DataFrame(index=ix)
        X["const"] = 1.0
        X["hdd"] = np.clip(heat_base - t, 0, None)
        X["cdd"] = np.clip(t - cool_base, 0, None)
        for d in range(1, 7):
            X[f"dow{d}"] = (ix.dayofweek == d).astype(float)
        X["xmas"] = (((ix.month == 12) & (ix.day >= 22)) | ((ix.month == 1) & (ix.day <= 6))).astype(float)
        X["summer"] = ((ix.month == 8)).astype(float)
        return X

    X = design(df.index, df["t"].to_numpy())
    trend = (df.index.year + df.index.dayofyear / 366.0).to_numpy() - 2020
    X["trend"] = trend
    beta, *_ = np.linalg.lstsq(X.to_numpy(), df["y"].to_numpy(), rcond=None)
    coef = pd.Series(beta, X.columns)
    resid = df["y"] - X.to_numpy() @ beta
    r2 = 1 - resid.var() / df["y"].var()

    def predict(ix, t, ref_year=2024.5):
        Xp = design(ix, np.asarray(t))
        Xp["trend"] = ref_year - 2020  # demand level frozen at the reference year
        return pd.Series(Xp.to_numpy() @ beta, ix)

    return coef, r2, predict


def era5_daily(var: str) -> pd.DataFrame:
    d = obs.c3s(var)
    return d.resample("1D").mean()
