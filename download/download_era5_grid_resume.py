"""Restartable version of download_era5_grid.py that can resume a request already queued at CDS (sequential: CDS
rejects more than one queued request per user for this dataset).

A month whose request is already queued at CDS (job ID given as argument month=jobid) is not resubmitted; its result
is downloaded when ready. Same requests and files as download_era5_grid.py; finished files are skipped.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ecmwf.datastores import Client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_era5_grid import AREA, LOG, MONTHS, OUT, VARS, log  # noqa: E402

EXISTING = dict(a.split("=") for a in sys.argv[1:])  # e.g. 201701=<job id>


def one(client: Client, y: int, m: int) -> None:
    target = OUT / f"era5_{y}{m:02d}.grib"
    if target.exists() and target.stat().st_size > 0:
        return
    key = f"{y}{m:02d}"
    for attempt in range(1, 4):
        try:
            if key in EXISTING and attempt == 1:
                remote = client.get_remote(EXISTING[key])
                log(f"waiting for queued job {remote.request_id} ({target.name})")
            else:
                req = {"product_type": ["reanalysis"], "variable": VARS, "year": [str(y)], "month": [f"{m:02d}"],
                       "day": [f"{d:02d}" for d in range(1, 32)], "time": [f"{h:02d}:00" for h in range(24)],
                       "area": AREA, "data_format": "grib", "download_format": "unarchived"}
                remote = client.submit("reanalysis-era5-single-levels", req)
                log(f"queued {target.name} as {remote.request_id}")
            part = target.with_suffix(".part")
            remote.download(str(part))
            part.replace(target)
            log(f"done {target.name} {target.stat().st_size} bytes")
            return
        except Exception as e:
            log(f"error {target.name}: {str(e)[:300]}")
            time.sleep(120 * attempt)


def client_from_cdsapirc() -> Client:
    cfg = dict(line.split(":", 1) for line in (Path.home() / ".cdsapirc").read_text().splitlines() if ":" in line)
    return Client(url=cfg["url"].strip(), key=cfg["key"].strip())


def main() -> None:
    client = client_from_cdsapirc()
    with ThreadPoolExecutor(1) as ex:  # CDS allows one queued request per user for this dataset
        list(ex.map(lambda ym: one(client, *ym), MONTHS))
    log("ALL DONE")


if __name__ == "__main__":
    main()
