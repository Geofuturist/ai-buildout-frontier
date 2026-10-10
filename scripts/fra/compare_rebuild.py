r"""Check that a rebuild did not change the France layers (SPEC_FRA r5 §6 p.4).

Before the rebuild, copy the current CSVs:  copy data\fra\layer_*.csv research\fra\before_rules\
Then run, from the repo root:               python scripts\fra\compare_rebuild.py

For each layer the newest data\fra\layer_<layer>_*.csv is compared with the copy:
- generation, consumption, transmission: byte for byte;
- icpe: byte for byte after dropping the new column selection_rule (SPEC_FRA r6) and checked_at
  (the build date). Everything else must be identical.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

REPO = Path.cwd()
OLD = REPO / "research" / "fra" / "before_rules"
NEW = REPO / "data" / "fra"
LAYERS = ["generation_odre", "consumption_agenceore", "transmission_rte", "icpe_georisques"]
ICPE_SKIP = ["selection_rule", "checked_at"]


def newest(folder: Path, layer: str) -> Path | None:
    files = sorted(folder.glob(f"layer_{layer}_*.csv"))
    return files[-1] if files else None


def icpe_bytes(p: Path) -> bytes:
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    df = df.drop(columns=[c for c in ICPE_SKIP if c in df.columns])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def main() -> None:
    bad = 0
    for layer in LAYERS:
        o, n = newest(OLD, layer), newest(NEW, layer)
        if o is None or n is None:
            print(f"{layer}: НЕТ ФАЙЛА (до: {o}, после: {n})")
            bad += 1
            continue
        if layer == "icpe_georisques":
            same = icpe_bytes(o) == icpe_bytes(n)
            how = "побайтово без selection_rule и checked_at"
        else:
            same = o.read_bytes() == n.read_bytes()
            how = "побайтово"
        print(f"{layer}: {'СОВПАЛИ' if same else 'РАЗЛИЧАЮТСЯ'} ({how}); {o.name} -> {n.name}")
        bad += 0 if same else 1
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
