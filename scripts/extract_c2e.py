"""Extract the Climate2Energy series used here from only_csv.zip to parquet (about 1 GB, minutes)."""
import sys
import time

from stress.c2e import PERIODS, REALIZATIONS, VARIABLES, extract

core = ["pv", "wind_on", "wind_off", "heat", "heat_full", "cool", "ror", "inflow"]
extra = [v for v in VARIABLES if v not in core]
for v in core + (extra if "--all" in sys.argv else []):
    for p in PERIODS:
        for r in REALIZATIONS:
            t = time.time()
            try:
                path = extract(v, r, p)
                print(f"{v} {p} {r}{r} -> {path.name} ({time.time() - t:.0f}s)", flush=True)
            except FileNotFoundError as e:
                print("missing:", e, flush=True)
print("ALL DONE")
