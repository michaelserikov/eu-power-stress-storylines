"""Faster ENTSO-E download: same queries as download_entsoe.py, but one request per year and 4 parallel workers.

The API accepts one-year periods for A44, A65 and A75. A year is skipped when its yearly file exists or when all 12
monthly files from download_entsoe.py exist. Yearly files: <...>/<key>_<YYYY>.xml.gz (gzip XML, may hold several
TimeSeries). Run with the de-wind-solar-nowcast venv; restartable.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_entsoe import AREA, CACHE, GEN_TYPES, PRICE, fetch, log, token  # noqa: E402


def year_jobs(key: str):
    jobs = []
    period = lambda a, b: {"periodStart": a.strftime("%Y%m%d%H%M"), "periodEnd": b.strftime("%Y%m%d%H%M")}
    # countries most needed first
    order = ["DE", "FR", "NL", "BE", "AT", "CH", "PL", "CZ", "DK", "NO", "SE", "FI", "GB", "IE", "ES", "PT", "IT"]
    cs = order + [c for c in AREA if c not in order]
    for c in cs:
        for z in PRICE[c]:
            for y in range(2015, 2026):
                a, b = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
                if z == "10Y1001A1001A63L":
                    if y > 2018:
                        continue
                    b = min(b, pd.Timestamp("2018-10-01"))
                if z == "10Y1001A1001A82H":
                    if y < 2018:
                        continue
                    a = max(a, pd.Timestamp("2018-10-01"))
                d = CACHE / "price" / c
                monthly = [d / f"{z}_{m:%Y%m}.xml.gz" for m in pd.date_range(a, b, freq="MS", inclusive="left")]
                if all(p.exists() for p in monthly):
                    continue
                jobs.append(({"securityToken": key, "documentType": "A44", "in_Domain": z, "out_Domain": z,
                              **period(a, b)}, d / f"{z}_{y}.xml.gz"))
    for c in cs:
        area = AREA[c]
        for y in range(2020, 2026):
            a, b = max(pd.Timestamp(f"{y}-01-01"), pd.Timestamp("2020-10-01")), pd.Timestamp(f"{y + 1}-01-01")
            jobs.append(({"securityToken": key, "documentType": "A65", "processType": "A16",
                          "outBiddingZone_Domain": area, **period(a, b)}, CACHE / "load" / c / f"Y{y}.xml.gz"))
            for t in GEN_TYPES:
                jobs.append(({"securityToken": key, "documentType": "A75", "processType": "A16", "in_Domain": area,
                              "psrType": t, **period(a, b)}, CACHE / "gen" / c / f"Y{y}_{t}.xml.gz"))
    return jobs


def main() -> None:
    jobs = year_jobs(token())
    log(f"fast: {len(jobs)} yearly requests")
    with ThreadPoolExecutor(4) as ex:
        for i, _ in enumerate(ex.map(lambda j: fetch(*j), jobs)):
            if i % 50 == 0:
                log(f"fast: {i}/{len(jobs)}")
    log("ALL DONE")


if __name__ == "__main__":
    main()
