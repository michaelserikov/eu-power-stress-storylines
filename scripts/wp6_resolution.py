"""WP6: what does climate-model resolution change in Climate2Energy-style capacity factors and event statistics?

Climate2Energy bias-corrects CESM2 on its own grid (1.25 x 0.94 deg) against ERA5 regridded to that grid, so a
perfectly corrected CESM2 behaves like ERA5 seen at 1.25 x 0.94 deg. The test therefore converts the same ERA5 hours
twice: on the native 0.25 deg grid and after averaging u, v, temperature and radiation to 1.25 x 0.94 deg boxes.
Conversion in the C2E style, simplified: 100 m wind extrapolated to 129 m hub height (power law, alpha 1/7), a
generic low-specific-power curve (cut-in 3, rated 9.5, cut-out 25 m/s, Gaussian smoothing 1 m/s), sites better than
the national median kept (as in C2E); PV from horizontal irradiance with a -0.4%/K temperature loss. Countries from
the CLIMADA national ID raster (onshore only). Windows: December 2016 - February 2017 and November 2024 - January
2025 (months available locally). Outputs: results/wp6, figures/wp6_resolution.png.
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from scipy.ndimage import gaussian_filter1d

from stress import events as ev
from stress.paths import FIGURES, RAW, RESULTS

OUT = RESULTS / "wp6"
OUT.mkdir(parents=True, exist_ok=True)
NATID = Path(os.environ.get("NATID_GRID", Path.home() / "climada" / "data" / "NatID_grid_0150as.nc"))
NATREG = NATID.parent / "NatRegIDs.csv"
ISO3 = {"AUT": "AT", "BEL": "BE", "BGR": "BG", "CHE": "CH", "CZE": "CZ", "DEU": "DE", "DNK": "DK", "EST": "EE",
        "ESP": "ES", "FIN": "FI", "FRA": "FR", "GBR": "GB", "GRC": "GR", "HRV": "HR", "HUN": "HU", "IRL": "IE",
        "ITA": "IT", "LTU": "LT", "LVA": "LV", "NLD": "NL", "NOR": "NO", "POL": "PL", "PRT": "PT", "ROU": "RO",
        "SRB": "RS", "SWE": "SE", "SVN": "SI", "SVK": "SK", "ALB": "AL", "BIH": "BA", "MNE": "ME", "MKD": "MK"}
HUB, ALPHA = 129.0, 1 / 7


def power_curve():
    v = np.arange(0, 40.01, 0.01)
    p = np.where(v < 3, 0, np.where(v < 9.5, (v**3 - 27) / (9.5**3 - 27), np.where(v < 25, 1.0, 0.0)))
    return v, gaussian_filter1d(p, 100)  # sigma 1 m/s on a 0.01 m/s grid


V, P = power_curve()


def cf_wind(speed100):
    s = speed100 * (HUB / 100.0) ** ALPHA
    return np.interp(s, V, P)


def cf_pv(ssrd_wm2, t2m_c):
    return np.clip(ssrd_wm2 / 1000.0 * (1 - 0.004 * (t2m_c + 0.03 * ssrd_wm2 - 25)), 0, 1)


def country_grid(lat, lon):
    ds = xr.open_dataset(NATID)
    g = ds["NatIdGrid"].sel(lat=xr.DataArray(lat, dims="lat"), lon=xr.DataArray(lon, dims="lon"), method="nearest")
    ids = pd.read_csv(NATREG).set_index("ID")["ISO"]
    arr = g.to_numpy()
    out = np.full(arr.shape, "", dtype=object)
    for i, iso in ids.items():
        if iso in ISO3:
            out[arr == i] = ISO3[iso]
    return out


def coarse_index(lat, lon):
    """Box index (1.25 deg lon x 0.9424 deg lat, anchored at 35N / 15W) for each fine cell."""
    li = np.floor((lat - lat.min()) / 0.9424).astype(int)
    lj = np.floor((lon - lon.min()) / 1.25 + 1e-9).astype(int)
    return li, lj


def coarsen(a, li, lj):
    """Average a (time, lat, lon) array over boxes and broadcast back to the fine grid."""
    nt = a.shape[0]
    ni, nj = li.max() + 1, lj.max() + 1
    out = np.zeros((nt, ni, nj), dtype="float64")
    cnt = np.zeros((ni, nj))
    for i in range(len(li)):
        for j in range(len(lj)):
            out[:, li[i], lj[j]] += a[:, i, j]
            cnt[li[i], lj[j]] += 1
    out /= cnt[None]
    return out[:, li][:, :, lj].astype("float32")


def load_month(path):
    kw = {"indexpath": ""}
    inst = xr.open_dataset(path, engine="cfgrib", backend_kwargs={**kw, "filter_by_keys": {"stepType": "instant"}})
    acc = xr.open_dataset(path, engine="cfgrib", backend_kwargs={**kw, "filter_by_keys": {"shortName": "ssrd"}})
    st = acc["ssrd"].stack(t=("time", "step")).transpose("t", "latitude", "longitude")
    vt = pd.DatetimeIndex(acc["valid_time"].stack(t=("time", "step")).to_numpy())
    arr = st.to_numpy() / 3600.0  # J/m2 accumulated over the hour -> W/m2
    pos = pd.Series(np.arange(len(vt)), vt)
    pos = pos[~pos.index.duplicated()]
    t = pd.DatetimeIndex(inst["time"].to_numpy())
    k = pos.reindex(t).to_numpy()
    rad = np.zeros((len(t),) + arr.shape[1:], dtype="float32")
    ok = ~np.isnan(k)
    rad[ok] = np.nan_to_num(arr[k[ok].astype(int)])
    u, v = inst["u100"].to_numpy(), inst["v100"].to_numpy()
    return t, inst.latitude.to_numpy(), inst.longitude.to_numpy(), u, v, inst["t2m"].to_numpy() - 273.15, rad


def country_series(cf, countries, select):
    out = {}
    for c in np.unique(countries[countries != ""]):
        m = (countries == c) & select
        if m.sum() >= 2:
            out[c] = cf[:, m].mean(axis=1)
    return out


def main():
    files = sorted((RAW / "era5_grid").glob("era5_*.grib"))
    res = {"fine": {"wind": [], "pv": []}, "coarse": {"wind": [], "pv": []}}
    times = []
    countries = None
    for f in files:
        t, lat, lon, u, v, t2, rad = load_month(f)
        if countries is None:
            countries = country_grid(lat, lon)
            li, lj = coarse_index(lat, lon)
        spd_f = np.sqrt(u**2 + v**2)
        uc, vc = coarsen(u, li, lj), coarsen(v, li, lj)
        spd_c = np.sqrt(uc**2 + vc**2)
        t2c, radc = coarsen(t2, li, lj), coarsen(rad, li, lj)
        res["fine"]["wind"].append(cf_wind(spd_f).astype("float32"))
        res["coarse"]["wind"].append(cf_wind(spd_c).astype("float32"))
        res["fine"]["pv"].append(cf_pv(rad, t2).astype("float32"))
        res["coarse"]["pv"].append(cf_pv(radc, t2c).astype("float32"))
        times.append(t)
        print(f.name, flush=True)
    idx = pd.DatetimeIndex(np.concatenate(times))
    series = {}
    for grid in res:
        w = np.concatenate(res[grid]["wind"])
        pv = np.concatenate(res[grid]["pv"])
        mean_cf = w.mean(axis=0)
        sel = np.zeros_like(mean_cf, dtype=bool)
        for c in np.unique(countries[countries != ""]):
            m = countries == c
            sel |= m & (mean_cf >= np.median(mean_cf[m]))  # sites better than the national median
        series[(grid, "wind")] = pd.DataFrame(country_series(w, countries, sel), index=idx)
        series[(grid, "wind_all")] = pd.DataFrame(country_series(w, countries, np.ones_like(sel)), index=idx)
        series[(grid, "pv")] = pd.DataFrame(country_series(pv, countries, np.ones_like(sel)), index=idx)
    for k, d in series.items():
        d.to_parquet(OUT / f"cf_{k[0]}_{k[1]}.parquet")
    rows = []
    windows = {"DJF 2016/17": ("2016-12-01", "2017-02-28 23:00"), "NDJ 2024/25": ("2024-11-01", "2025-01-31 23:00")}
    for wname, (a, b) in windows.items():
        for c in series[("fine", "wind")].columns:
            f_, c_ = series[("fine", "wind")][c].loc[a:b], series[("coarse", "wind")][c].loc[a:b]
            fa, ca = series[("fine", "wind_all")][c].loc[a:b], series[("coarse", "wind_all")][c].loc[a:b]
            fp, cp = series[("fine", "pv")][c].loc[a:b], series[("coarse", "pv")][c].loc[a:b]
            if len(f_) == 0:
                continue
            low_f = ev.low_events(f_, 0.10, min_len=24)
            low_c = ev.low_events(c_, 0.10, min_len=24)
            rows.append({"window": wname, "country": c, "wind_mean_fine": f_.mean(), "wind_mean_coarse": c_.mean(),
                         "wind_mean_allsites_fine": fa.mean(), "wind_mean_allsites_coarse": ca.mean(),
                         "wind_std_fine": f_.std(), "wind_std_coarse": c_.std(), "wind_corr": f_.corr(c_),
                         "hours_below_10pct_fine": int((f_ < 0.10).sum()), "hours_below_10pct_coarse": int((c_ < 0.10).sum()),
                         "lowwind_events_24h_fine": len(low_f), "lowwind_events_24h_coarse": len(low_c),
                         "longest_lowwind_h_fine": int(low_f.duration.max()) if len(low_f) else 0,
                         "longest_lowwind_h_coarse": int(low_c.duration.max()) if len(low_c) else 0,
                         "pv_mean_fine": fp.mean(), "pv_mean_coarse": cp.mean()})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "resolution_by_country.csv", index=False)
    summ = df.drop(columns="country").groupby("window").median()
    summ.to_csv(OUT / "resolution_median.csv")
    print(summ.T.round(3).to_string())
    plot(df, series)


def plot(df, series):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    ax = axes[0]
    ax.scatter(df.wind_mean_fine, df.wind_mean_coarse, s=12)
    lim = [0, max(df.wind_mean_fine.max(), df.wind_mean_coarse.max()) * 1.05]
    ax.plot(lim, lim, "k--", lw=0.7)
    ax.set_xlabel("mean wind CF, ERA5 0.25 deg")
    ax.set_ylabel("mean wind CF, 1.25 x 0.94 deg")
    ax = axes[1]
    ax.scatter(df.hours_below_10pct_fine, df.hours_below_10pct_coarse, s=12)
    lim = [0, max(df.hours_below_10pct_fine.max(), df.hours_below_10pct_coarse.max()) * 1.05]
    ax.plot(lim, lim, "k--", lw=0.7)
    ax.set_xlabel("hours with wind CF < 10%, 0.25 deg")
    ax.set_ylabel("same, 1.25 x 0.94 deg")
    ax = axes[2]
    full = series[("fine", "wind")]["DE"]
    has_2024 = len(full.loc["2024-11-01":"2024-12-20"]) > 0
    a, b = ("2024-11-01", "2024-12-20") if has_2024 else (str(full.index[0].date()), str((full.index[0] + pd.Timedelta("31D")).date()))
    for grid, col in [("fine", "tab:blue"), ("coarse", "tab:red")]:
        s = series[(grid, "wind")]["DE"].loc[a:b]
        ax.plot(s.index, s, color=col, lw=0.8, label="0.25 deg" if grid == "fine" else "1.25 x 0.94 deg")
    ax.set_title(f"Germany, onshore wind CF, {a} to {b}", fontsize=9)
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", labelsize=7, rotation=30)
    fig.suptitle("Resolution test: the same ERA5 hours converted on the native and on a CESM2-like grid", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / "wp6_resolution.png", dpi=150)


if __name__ == "__main__":
    main()
