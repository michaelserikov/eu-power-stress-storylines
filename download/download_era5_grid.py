"""ERA5 0.25 deg hourly fields over Europe for the resolution test (Climate2Energy on native vs CESM2 grid).

Two stress windows: winter 2016/17 (January 2017 cold spell) and November 2024 - January 2025 (Dunkelflaute).
Variables as used by Climate2Energy bias correction: 100 m wind, surface solar radiation downwards, 2 m temperature.
One GRIB file per month in data_voland/raw/era5_grid; finished files are skipped.
"""
from __future__ import annotations

import time
from pathlib import Path

import cdsapi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "era5_grid"
LOG = ROOT / "logs" / "era5_grid.log"
MONTHS = [(2016, 12), (2017, 1), (2017, 2), (2024, 11), (2024, 12), (2025, 1)]
VARS = ["100m_u_component_of_wind", "100m_v_component_of_wind", "surface_solar_radiation_downwards", "2m_temperature"]
AREA = [72, -15, 35, 35]  # N, W, S, E


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as h:
        h.write(line + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client(quiet=True, progress=False)
    for y, m in MONTHS:
        target = OUT / f"era5_{y}{m:02d}.grib"
        if target.exists() and target.stat().st_size > 0:
            continue
        req = {"product_type": ["reanalysis"], "variable": VARS, "year": [str(y)], "month": [f"{m:02d}"],
               "day": [f"{d:02d}" for d in range(1, 32)], "time": [f"{h:02d}:00" for h in range(24)],
               "area": AREA, "data_format": "grib", "download_format": "unarchived"}
        for attempt in range(1, 6):
            part = target.with_suffix(".part")
            try:
                log(f"start {target.name} (attempt {attempt})")
                client.retrieve("reanalysis-era5-single-levels", req).download(str(part))
                part.replace(target)
                log(f"done {target.name} {target.stat().st_size} bytes")
                break
            except Exception as e:  # CDS fails transiently; retry, then move on
                log(f"error {target.name}: {e}")
                time.sleep(60 * attempt)
    log("ALL DONE")


if __name__ == "__main__":
    main()
