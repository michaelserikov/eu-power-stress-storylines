"""Rerun the whole analysis in order (raw data must be in place, see DATA.md). Usage: python scripts/run_all.py [v0.1|v0.2|v0.3]"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STEPS = {
    "v0.1": ["extract_c2e.py", "wp1_real_events.py", "wp1_era5_vs_c2e.py", "wp3_netload_events.py", "wp3_country.py"],
    "v0.2": ["wp2_patterns.py", "wp4_technology.py", "wp5_mitigation.py", "wp5_pypsa.py"],
    "v0.3": ["wp6_resolution.py", "v03_nordic_hydro.py"],
}
upto = sys.argv[1] if len(sys.argv) > 1 else "v0.3"
for version, scripts in STEPS.items():
    for s in scripts:
        print(f"== {version}: {s}", flush=True)
        subprocess.run([sys.executable, str(HERE / s)], check=True)
    if version == upto:
        break
