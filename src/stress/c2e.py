"""Read Climate2Energy (Zenodo 15269455, only_csv.zip) series straight from the archive into parquet.

Archive layout: only_csv/{X}/{period}/{Y}/output_variables/<file>.csv, where X is the realization used for the bias
correction and Y the realization whose output is stored; the three realizations are the diagonal AA, BB, CC
(A random member, B max NAO, C min NAO). Files are wide: one row per country, one column per hour (UTC, hour-ending).
Wind and PV are capacity factors (0-1), heating and cooling demand GWh per hour, run-of-river GWh per day,
reservoir inflow GWh per week.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd

from .paths import C2E, C2E_ZIP

REALIZATIONS = ("A", "B", "C")
PERIODS = {"historical": range(1995, 2015), "SSP370": range(2080, 2100)}
# variable key -> file name pattern ({y} = year)
VARIABLES = {
    "pv": "PV_{y}.csv",
    "wind_on": "Wind-power_{y}_SWT142_3150_onshore_True_density_corrected.csv",
    "wind_off": "Wind-power_{y}_E-126_7580_onshore_False_density_corrected.csv",
    "wind_on_e126": "Wind-power_{y}_E-126_7580_onshore_True_density_corrected.csv",
    "wind_on_swt120": "Wind-power_{y}_SWT120_3600_onshore_True_density_corrected.csv",
    "heat": "heating-demand_{y}.csv",
    "heat_full": "heating-demand_{y}_fully-electrified.csv",
    "cool": "cooling-demand_{y}.csv",
    "ror": "hydro_ror_{y}.csv",
    "inflow": "hydro_inflow_{y}.csv",
}


def member(path: str, x: str, period: str, y: str) -> str:
    return f"only_csv/{x}/{period}/{y}/output_variables/{path}"


def read_member(z: zipfile.ZipFile, name: str) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(z.read(name)), index_col=0)
    df = df.T
    df.index = pd.to_datetime(df.index)
    df.columns.name = None
    return df.astype("float32")


def extract(variable: str, realization: str, period: str, bc: str | None = None, out: Path = C2E) -> Path:
    """Concatenate all years of one variable into data/c2e/<period>_<bc><real>_<variable>.parquet."""
    bc = bc or realization
    target = out / f"{period}_{bc}{realization}_{variable}.parquet"
    if target.exists():
        return target
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(C2E_ZIP) as z:
        names = set(z.namelist())
        parts = []
        for y in PERIODS[period]:
            name = member(VARIABLES[variable].format(y=y), bc, period, realization)
            if name in names:
                parts.append(read_member(z, name))
    if not parts:
        raise FileNotFoundError(f"no files for {variable} {bc}{realization} {period}")
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    df.to_parquet(target)
    return target


def load(variable: str, realization: str, period: str, bc: str | None = None) -> pd.DataFrame:
    return pd.read_parquet(extract(variable, realization, period, bc))


def countries() -> list[str]:
    return list(load("pv", "A", "historical").columns)
