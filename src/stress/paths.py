"""Data locations. Override with environment variables when the raw data live elsewhere."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("STRESS_DATA", ROOT / "data"))
C2E_ZIP = Path(os.environ.get("C2E_ZIP", Path.home() / "data_c2e" / "only_csv.zip"))
RAW = Path(os.environ.get("STRESS_RAW", Path.home() / "data_voland" / "raw"))
OPSD = Path(os.environ.get("OPSD_CSV", Path.home() / "eu-weather-years-pypsa" / "data" / "raw" / "time_series_60min_singleindex.csv"))
MSLP = Path(os.environ.get("MSLP_DIR", Path.home() / "de-windstorm-risk" / "data" / "raw" / "era5_mslp_cloud"))
C2E = DATA / "c2e"
DERIVED = DATA / "derived"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
