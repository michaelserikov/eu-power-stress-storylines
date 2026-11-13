"""Write SHA-256 checksums of the raw inputs to data_manifest.csv (one line per file; ENTSO-E cache as one digest)."""
import hashlib
import sys
from pathlib import Path

from stress.paths import C2E_ZIP, MSLP, OPSD, RAW


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


rows = []
for p in [C2E_ZIP, OPSD, *sorted((RAW / "c3s_country").glob("*.zip")), *sorted((RAW / "era5_grid").glob("*.grib")),
          *sorted(MSLP.glob("mslp_*.npz"))]:
    rows.append((p.name, p.stat().st_size, sha(p)))
h = hashlib.sha256()
files = sorted((RAW / "entsoe").rglob("*.xml.gz"))
for p in files:
    h.update(p.relative_to(RAW).as_posix().encode())
    h.update(p.read_bytes())
rows.append((f"entsoe cache ({len(files)} files)", sum(p.stat().st_size for p in files), h.hexdigest()))
out = Path(__file__).resolve().parents[1] / "data_manifest.csv"
out.write_text("file,bytes,sha256\n" + "".join(f"{a},{b},{c}\n" for a, b, c in rows))
print(out.read_text() if "-v" in sys.argv else f"{len(rows)} entries")
