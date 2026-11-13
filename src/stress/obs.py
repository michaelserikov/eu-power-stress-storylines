"""Observed data: C3S ERA5-based country series, OPSD time series (2015 to 2020-09) and ENTSO-E Transparency XML.

All series are returned hourly in UTC with ISO-2 country codes as columns (GB for the United Kingdom, GR for Greece).
"""
from __future__ import annotations

import gzip
import io
import re
import zipfile
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

from .paths import DERIVED, OPSD, RAW

NAME_TO_ISO = {
    "Albania": "AL", "Austria": "AT", "Bosnia and Herzegovina": "BA", "Belgium": "BE", "Bulgaria": "BG",
    "Switzerland": "CH", "Czech Republic": "CZ", "Germany": "DE", "Denmark": "DK", "Estonia": "EE", "Spain": "ES",
    "Finland": "FI", "France": "FR", "Greece": "GR", "Croatia": "HR", "Hungary": "HU", "Ireland": "IE", "Italy": "IT",
    "Lithuania": "LT", "Latvia": "LV", "Montenegro": "ME", "Macedonia": "MK", "Netherlands": "NL", "Norway": "NO",
    "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Serbia": "RS", "Sweden": "SE", "Slovenia": "SI",
    "Slovakia": "SK", "United Kingdom": "GB",
}
C2E_COUNTRIES = list(NAME_TO_ISO.values())
C3S_FIX = {"EL": "GR", "UK": "GB"}

# ---------------------------------------------------------------- C3S (sis-energy-derived-reanalysis, ERA5)
C3S_FILES = {"wind_on": "wind_onshore_cf.zip", "pv": "solar_pv_cf.zip", "wind_off": "wind_offshore_cf.zip",
             "t2m": "t2m.zip", "demand_daily": "demand_daily.zip"}


def c3s(var: str) -> pd.DataFrame:
    """C3S ERA5-based country series, cached as parquet in data/derived."""
    cache = DERIVED / f"c3s_{var}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    with zipfile.ZipFile(RAW / "c3s_country" / C3S_FILES[var]) as z:
        name = [n for n in z.namelist() if n.endswith(".csv")][0]
        text = z.read(name).decode()
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    df = pd.read_csv(io.StringIO("\n".join(lines)), index_col=0, parse_dates=True)
    df = df.rename(columns=lambda c: C3S_FIX.get(c, c))
    df = df[[c for c in df.columns if c in C2E_COUNTRIES]].astype("float32")
    if var == "pv":
        df = df.reindex(pd.date_range(df.index.min().normalize(), df.index.max(), freq="1h")).fillna(0.0)
    if var == "t2m" and df.mean().mean() > 200:
        df = df - 273.15
    DERIVED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    return df


# ---------------------------------------------------------------- OPSD
@lru_cache(maxsize=1)
def _opsd() -> pd.DataFrame:
    cache = DERIVED / "opsd.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    df = pd.read_csv(OPSD, index_col="utc_timestamp", parse_dates=True, low_memory=False)
    df = df.drop(columns=[c for c in df.columns if c == "cet_cest_timestamp"])
    df.index = df.index.tz_convert(None) if df.index.tz is not None else df.index
    df = df.select_dtypes("number").astype("float32")
    DERIVED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    return df


def opsd(kind: str) -> pd.DataFrame:
    """kind: load, wind_on, wind_off, wind, solar, price. Country-level columns only (ISO-2)."""
    suffix = {"load": "_load_actual_entsoe_transparency", "wind_on": "_wind_onshore_generation_actual",
              "wind_off": "_wind_offshore_generation_actual", "wind": "_wind_generation_actual",
              "solar": "_solar_generation_actual", "price": "_price_day_ahead"}[kind]
    d = _opsd()
    out = {}
    for c in d.columns:
        if c.endswith(suffix):
            code = c[: -len(suffix)]
            if code in C2E_COUNTRIES or code in ("GB_GBN", "DE_LU", "DE_AT_LU"):
                out[code] = d[c]
    df = pd.DataFrame(out)
    if "GB" not in df and "GB_GBN" in df:
        df["GB"] = df.pop("GB_GBN")
    return df


# ---------------------------------------------------------------- ENTSO-E Transparency XML
_RES = {"PT15M": "15min", "PT30M": "30min", "PT60M": "60min", "P1D": "1D"}


def parse_entsoe(path: Path, generation_only: bool = False) -> pd.Series:
    """Parse one gzip XML document (A44, A65 or A75) into an hourly mean series (UTC, naive).

    A75 documents can hold consumption series (outBiddingZone) next to generation (inBiddingZone); with
    generation_only, only the latter are kept."""
    raw = gzip.decompress(path.read_bytes())
    if b"Acknowledgement_MarketDocument" in raw[:400]:
        return pd.Series(dtype="float64")
    root = ET.fromstring(raw)
    ns = re.match(r"\{.*\}", root.tag).group(0)
    parts = []
    for ts in root.iter(f"{ns}TimeSeries"):
        if generation_only and next(ts.iter(f"{ns}inBiddingZone_Domain.mRID"), None) is None:
            continue
        for period in ts.iter(f"{ns}Period"):
            start = pd.Timestamp(period.find(f"{ns}timeInterval/{ns}start").text).tz_convert(None)
            end = pd.Timestamp(period.find(f"{ns}timeInterval/{ns}end").text).tz_convert(None)
            freq = _RES[period.find(f"{ns}resolution").text]
            idx = pd.date_range(start, end, freq=freq, inclusive="left")
            vals = np.full(len(idx), np.nan)
            for p in period.iter(f"{ns}Point"):
                pos = int(p.find(f"{ns}position").text) - 1
                q = p.find(f"{ns}price.amount")
                q = q if q is not None else p.find(f"{ns}quantity")
                if 0 <= pos < len(vals):
                    vals[pos] = float(q.text)
            s = pd.Series(vals, idx).ffill()  # curve type A03 omits repeated values
            parts.append(s)
    if not parts:
        return pd.Series(dtype="float64")
    s = pd.concat(parts)
    s = s.groupby(level=0).mean()
    return s.resample("1h").mean()


def entsoe(kind: str, country: str, psr: str | None = None) -> pd.Series:
    """kind: price (2015-2025), load or gen (2020-10 to 2025, gen needs psr B16 solar, B18 offshore, B19 onshore)."""
    base = RAW / "entsoe" / kind / country
    if not base.exists():
        return pd.Series(dtype="float64", name=country)
    files = sorted(base.glob("*.xml.gz"))
    if psr:
        files = [f for f in files if f.name.endswith(f"_{psr}.xml.gz")]
    parts = [parse_entsoe(f, generation_only=(kind == "gen")) for f in files]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.Series(dtype="float64", name=country)
    s = pd.concat(parts)
    s = s.groupby(level=0).mean().sort_index()
    s.name = country
    return s


def entsoe_panel(kind: str, psr: str | None = None, countries=None) -> pd.DataFrame:
    tag = f"entsoe_{kind}{'_' + psr if psr else ''}"
    cache = DERIVED / f"{tag}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    cs = countries or C2E_COUNTRIES
    series = {c: entsoe(kind, c, psr) for c in cs}
    df = pd.DataFrame({c: v for c, v in series.items() if len(v)}).astype("float32")
    df = df.dropna(axis=1, how="all")
    return df


def save_entsoe_panels() -> None:
    """Cache parsed ENTSO-E panels once the download is complete."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    for kind, psr in [("price", None), ("load", None), ("gen", "B16"), ("gen", "B18"), ("gen", "B19")]:
        df = entsoe_panel(kind, psr)
        df.to_parquet(DERIVED / f"entsoe_{kind}{'_' + psr if psr else ''}.parquet")
