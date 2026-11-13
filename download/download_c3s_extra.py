"""C3S requests the first script could not get: valid combinations per the CDS constraints (13 Nov 2026).

Offshore wind is only offered at maritime_country_level; demand only daily (not hourly); 2 m temperature hourly at
country level (used for the hourly demand model). Finished files are skipped.
"""
import time
from pathlib import Path

import cdsapi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "c3s_country"
LOG = ROOT / "logs" / "c3s_country.log"
JOBS = {
    "wind_offshore_cf": {"variable": ["wind_power_generation_offshore"], "energy_product_type": ["capacity_factor_ratio"],
                         "spatial_aggregation": ["maritime_country_level"], "temporal_aggregation": ["hourly"]},
    "demand_daily": {"variable": ["electricity_demand"], "energy_product_type": ["energy"],
                     "spatial_aggregation": ["country_level"], "temporal_aggregation": ["daily"]},
    "t2m": {"variable": ["2m_air_temperature"], "spatial_aggregation": ["country_level"],
            "temporal_aggregation": ["hourly"]},
}


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as h:
        h.write(line + "\n")


client = cdsapi.Client(quiet=True, progress=False)
for name, req in JOBS.items():
    target = OUT / f"{name}.zip"
    if target.exists() and target.stat().st_size > 0:
        continue
    for attempt in range(1, 4):
        try:
            log(f"start {name} (attempt {attempt})")
            client.retrieve("sis-energy-derived-reanalysis", req).download(str(target.with_suffix(".part")))
            target.with_suffix(".part").replace(target)
            log(f"done {name} {target.stat().st_size} bytes")
            break
        except Exception as e:
            log(f"error {name}: {str(e)[:300]}")
            time.sleep(60 * attempt)
log("EXTRA ALL DONE")
