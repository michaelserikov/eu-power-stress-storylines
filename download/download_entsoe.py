"""ENTSO-E Transparency data for the 32 Climate2Energy countries.

Load (A65/A16) and wind/solar actual generation (A75/A16; B16 solar, B18 wind offshore, B19 wind onshore)
from 2020-10 (OPSD covers 2015 to 2020-09), day-ahead prices (A44) for 2015-2025.
Raw XML cached gzip-compressed (.xml.gz) per query and month in data_voland/raw/entsoe; finished files are skipped, so the
script can be stopped and restarted. API key from ENTSOE_API_KEY or ~/.entsoe_token.
"""
from __future__ import annotations

import gzip
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "raw" / "entsoe"
LOG = ROOT / "logs" / "entsoe.log"
API = "https://web-api.tp.entsoe.eu/api"

# country -> area code for load and generation
AREA = {"AL": "10YAL-KESH-----5", "AT": "10YAT-APG------L", "BA": "10YBA-JPCC-----D", "BE": "10YBE----------2",
        "BG": "10YCA-BULGARIA-R", "CH": "10YCH-SWISSGRIDZ", "CZ": "10YCZ-CEPS-----N", "DE": "10Y1001A1001A83F",
        "DK": "10Y1001A1001A65H", "EE": "10Y1001A1001A39I", "ES": "10YES-REE------0", "FI": "10YFI-1--------U",
        "FR": "10YFR-RTE------C", "GR": "10YGR-HTSO-----Y", "HR": "10YHR-HEP------M", "HU": "10YHU-MAVIR----U",
        "IE": "10YIE-1001A00010", "IT": "10YIT-GRTN-----B", "LT": "10YLT-1001A0008Q", "LV": "10YLV-1001A00074",
        "ME": "10YCS-CG-TSO---S", "MK": "10YMK-MEPSO----8", "NL": "10YNL----------L", "NO": "10YNO-0--------C",
        "PL": "10YPL-AREA-----S", "PT": "10YPT-REN------W", "RO": "10YRO-TEL------P", "RS": "10YCS-SERBIATSOV",
        "SE": "10YSE-1--------K", "SI": "10YSI-ELES-----O", "SK": "10YSK-SEPS-----K", "GB": "10YGB----------A"}
# day-ahead price zones (one or two representative zones where a country is split)
PRICE = {**{c: [a] for c, a in AREA.items() if c not in {"DE", "DK", "IE", "IT", "NO", "SE", "GB"}},
         "DE": ["10Y1001A1001A63L", "10Y1001A1001A82H"],  # DE-AT-LU until 09/2018, DE-LU after
         "DK": ["10YDK-1--------W", "10YDK-2--------M"], "IE": ["10Y1001A1001A59C"],
         "IT": ["10Y1001A1001A73I"], "NO": ["10YNO-1--------2", "10YNO-2--------T"],
         "SE": ["10Y1001A1001A46L", "10Y1001A1001A47J"], "GB": ["10YGB----------A"]}
GEN_TYPES = ["B16", "B18", "B19"]


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as h:
        h.write(line + "\n")


def token() -> str:
    return os.environ.get("ENTSOE_API_KEY") or (Path.home() / ".entsoe_token").read_text(encoding="utf-8").strip()


def fetch(params: dict, path: Path) -> None:
    if path.exists():
        return
    body = None
    for attempt in range(5):
        try:
            req = Request(f"{API}?{urlencode(params)}", headers={"Accept-Encoding": "gzip"})  # about 24x less traffic
            with urlopen(req, timeout=180) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") != "gzip":
                    body = gzip.compress(body)
            break
        except HTTPError as e:
            raw = e.read()
            body = raw if e.headers.get("Content-Encoding") == "gzip" else gzip.compress(raw)
            if e.code in (429, 503):
                time.sleep(20 * (attempt + 1))
                body = None
                continue
            break  # 400 "no matching data" etc.: keep the answer so it is not asked again
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(20 * (attempt + 1))
    if body is None:
        log(f"failed {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    time.sleep(0.3)


def months(start: str, end: str):
    m = pd.date_range(start, end, freq="MS")
    return list(zip(m[:-1], m[1:]))


def main() -> None:
    key = token()
    period = lambda a, b: {"periodStart": a.strftime("%Y%m%d%H%M"), "periodEnd": b.strftime("%Y%m%d%H%M")}
    # prices first: small and needed for the real-event catalogue
    for c, zones in PRICE.items():
        for z in zones:
            for a, b in months("2015-01-01", "2026-01-01"):
                if z == "10Y1001A1001A63L" and a >= pd.Timestamp("2018-10-01"):
                    continue
                if z == "10Y1001A1001A82H" and a < pd.Timestamp("2018-10-01"):
                    continue
                fetch({"securityToken": key, "documentType": "A44", "in_Domain": z, "out_Domain": z, **period(a, b)},
                      CACHE / "price" / c / f"{z}_{a:%Y%m}.xml.gz")
        log(f"price {c} done")
    for c, area in AREA.items():
        for a, b in months("2020-10-01", "2026-01-01"):
            fetch({"securityToken": key, "documentType": "A65", "processType": "A16",
                   "outBiddingZone_Domain": area, **period(a, b)}, CACHE / "load" / c / f"{a:%Y%m}.xml.gz")
            for t in GEN_TYPES:
                fetch({"securityToken": key, "documentType": "A75", "processType": "A16", "in_Domain": area,
                       "psrType": t, **period(a, b)}, CACHE / "gen" / c / f"{a:%Y%m}_{t}.xml.gz")
        log(f"load+gen {c} done")
    log("ALL DONE")


if __name__ == "__main__":
    main()
