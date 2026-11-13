"""C3S country-level hourly capacity factors from ERA5 (sis-energy-derived-reanalysis) for the ERA5 vs C2E comparison.

Dataset is superseded by sis-energy-global-reanalysis (deprecated December 2026), so it is fetched now.
Files go to data_voland/raw/c3s_country; finished files are skipped.
"""
import time
from pathlib import Path

import cdsapi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "c3s_country"
LOG = ROOT / "logs" / "c3s_country.log"
JOBS = {"wind_onshore_cf": {"variable": ["wind_power_generation_onshore"], "energy_product_type": ["capacity_factor_ratio"]},
        "wind_offshore_cf": {"variable": ["wind_power_generation_offshore"], "energy_product_type": ["capacity_factor_ratio"]},
        "solar_pv_cf": {"variable": ["solar_photovoltaic_power_generation"], "energy_product_type": ["capacity_factor_ratio"]},
        "demand": {"variable": ["electricity_demand"], "energy_product_type": ["energy"]}}


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as h:
        h.write(line + "\n")


OUT.mkdir(parents=True, exist_ok=True)
client = cdsapi.Client(quiet=True, progress=False)
for name, fields in JOBS.items():
    target = OUT / f"{name}.zip"
    if target.exists() and target.stat().st_size > 0:
        continue
    req = {"spatial_aggregation": ["country_level"], "temporal_aggregation": ["hourly"], **fields}
    for attempt in range(1, 4):
        try:
            log(f"start {name} (attempt {attempt})")
            client.retrieve("sis-energy-derived-reanalysis", req).download(str(target.with_suffix(".part")))
            target.with_suffix(".part").replace(target)
            log(f"done {name} {target.stat().st_size} bytes")
            break
        except Exception as e:
            log(f"error {name}: {str(e)[:500]}")
            time.sleep(60 * attempt)
log("ALL DONE")
