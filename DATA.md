# Data

Raw data are not in the repository. Paths are set in `src/stress/paths.py` and can be overridden with environment variables (`C2E_ZIP`, `STRESS_RAW`, `OPSD_CSV`, `MSLP_DIR`, `NATID_GRID`, `NVE_JSON`). `data_manifest.csv` lists the SHA-256 checksum of every input file used for the results in this repository (`python scripts/checksums.py`).

| Source | What | Licence | How to get it |
|---|---|---|---|
| Climate2Energy, Zenodo record 15269455 | `only_csv.zip` (6.9 GB packed, 16.8 GB unpacked): country-level hourly wind and PV capacity factors, heating and cooling demand, daily run-of-river and weekly reservoir inflow; CESM2 realizations A, B, C, 1995-2014 and 2080-2099 (SSP3-7.0) | CC-BY 4.0 | download from Zenodo; `scripts/extract_c2e.py` reads the needed series straight from the zip (no full unpacking) |
| C3S `sis-energy-derived-reanalysis` | ERA5-based country capacity factors (onshore hourly, offshore hourly at maritime country level, PV hourly), daily demand, hourly 2 m temperature, 1979 to 09/2026 | Copernicus licence | `download/download_c3s_country.py`, `download/download_c3s_extra.py` (needs `~/.cdsapirc`) |
| ENTSO-E Transparency Platform | day-ahead prices 2015-2025 (A44), load (A65) and wind and solar generation (A75) 10/2020-2025, 32 countries | ENTSO-E terms of use | `download/download_entsoe_fast.py` (needs an API token); one request per year, gzip XML cache |
| Open Power System Data, time series 2020-10-06 | load, wind and solar by country, 2015 to 09/2020 | CC-BY 4.0 (ENTSO-E based) | opsd.org; the copy from eu-weather-years-pypsa is used |
| ERA5 mean sea level pressure | daily from 6-hourly, 1.5 deg, North Atlantic and Europe, 1990-2025 | Copernicus licence | cached by de-windstorm-risk (`download_mslp_cloud.py`) |
| ERA5 single levels, 0.25 deg | 100 m wind, surface solar radiation, 2 m temperature over Europe, Dec 2016-Feb 2017 and Nov 2024-Jan 2025 | Copernicus licence | `download/download_era5_grid.py` |
| NVE magasinstatistikk | weekly Norwegian reservoir filling 1995-2026 | NLOD | cached by nordic-hydro-unit-commitment |
| CLIMADA national ID grid | 150 arcsec country raster for masks | GPL-3 (CLIMADA data) | ships with CLIMADA |
| PyPSA model inputs | lines, buses, power plants, PyPSA technology-data costs 2030 | see eu-weather-years-pypsa | from that repository |

Known gaps: ENTSO-E publishes no GB data after Brexit, so GB is left out of the observed 2015-2025 panel; Dutch solar is largely missing in ENTSO-E A75, so the Dutch current fleet has almost no PV; C3S offers demand only daily, hence the own temperature model for hourly or daily demand.
