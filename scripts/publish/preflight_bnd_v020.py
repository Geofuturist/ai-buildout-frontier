r"""Read-only check of the CODE-BND output before the first dev build of abf-boundaries v0.2.0.

Run command (from the repository root, Windows):
    python scripts\publish\preflight_bnd_v020.py > preflight_bnd.txt

It changes nothing. It prints what the publication build expects to find and what is really there:
  1. columns and rows of display\contested_areas.parquet;
  2. verdicts in verified_against of the registry (countries outside USA, FRA, GBR, NOR);
  3. download date of the CLDR files in the meta.json of the BND output;
  4. the place of the CLDR LICENSE file (found by SHA-256);
  5. unit counts of display\adm0/adm1/adm2.parquet.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

BND = Path(r"D:\GISData\Boundaries\out\abf-boundaries-v0.2.0")
SOURCES = Path(r"D:\GISData\Boundaries\sources")
REGISTRY = Path("boundaries") / "boundary_registry.csv"
LICENSE_SHA = "b49d0e9f8ead51ca8b7df6fec89cc3ae6809198b4b9d43c74216da0118f23f5b"
NEED = ["area_id", "frame_unit_ids", "name", "controlled_by", "claimed_by", "control_since", "label",
        "source_control", "source_claim", "checked_at", "checked_by"]
# the layer of CODE-BND has six columns; these five are added by the publication from boundaries\contested_areas.csv
CSV_COLS = ["frame_unit_ids", "source_control", "source_claim", "checked_at", "checked_by"]
VERDICT = re.compile(r"verdict\W{0,3}(confirmed|disputed|refer_arch)\b", re.I)


def main() -> int:
    bad = 0
    print("== 1. display\\contested_areas.parquet")
    p = BND / "display" / "contested_areas.parquet"
    if p.exists():
        g = gpd.read_parquet(p)
        print("rows:", len(g), "| columns:", list(g.columns))
        missing = [c for c in NEED if c not in g.columns and c not in CSV_COLS]
        print("MISSING columns:" if missing else "OK: all expected columns are there", missing or "")
        bad += bool(missing)
        print(g.drop(columns="geometry").to_string(max_colwidth=40))
    else:
        print("MISSING file:", p); bad += 1

    print("\n== 2. registry verdicts")
    reg = pd.read_csv(REGISTRY, dtype=str, keep_default_na=False)
    adm1 = reg[(reg["level"].str.upper().isin(["ADM1", "1"])) & (reg["verified"].str.lower() == "true")]
    new = adm1[~adm1["iso3"].isin(["USA", "FRA", "GBR", "NOR"])]
    print("rows:", len(reg), "| verified ADM1 countries outside USA/FRA/GBR/NOR:", new["iso3"].nunique(), "(expected 104)")
    found = {r["iso3"]: VERDICT.findall(r["verified_against"]) for _, r in new.iterrows()}
    with_v = {k: v[-1].lower() for k, v in found.items() if v}
    cnt = {x: list(with_v.values()).count(x) for x in ("confirmed", "disputed", "refer_arch")}
    print("countries with a verdict:", len(with_v), cnt, "(expected 27: confirmed 22, disputed 3, refer_arch 2)")
    if len(with_v) != 27:
        bad += 1
        print("Example verified_against texts (first 3 without a verdict):")
        for k in [k for k, v in found.items() if not v][:3]:
            print(" ", k, "->", new[new.iso3 == k].iloc[0]["verified_against"][:200])

    print("\n== 3. CLDR in meta.json")
    mp = BND / "meta.json"
    if mp.exists():
        srcs = [s for s in json.loads(mp.read_text(encoding="utf-8")).get("sources", []) if "CLDR" in str(s.get("product", ""))]
        for s in srcs:
            print({k: s.get(k) for k in ("publisher", "product", "retrieved_at", "downloaded_at", "date", "sha256")})
        dates = {str(s.get(k))[:10] for s in srcs for k in ("retrieved_at", "downloaded_at", "date", "retrieved") if s.get(k)}
        print("distinct download days:", sorted(dates), "(need exactly one)")
        bad += len(dates) != 1 or len(srcs) != 4
    else:
        print("MISSING file:", mp); bad += 1

    print("\n== 4. CLDR LICENSE")
    hits = [q for q in SOURCES.rglob("*LICENSE*") if q.is_file() and hashlib.sha256(q.read_bytes()).hexdigest() == LICENSE_SHA] if SOURCES.exists() else []
    print("found:", [str(h) for h in hits] or "NOT FOUND (no *LICENSE* file with SHA-256 b49d0e9f... under " + str(SOURCES) + ")")
    bad += not hits

    print("\n== 5. unit counts")
    for lvl, want in (("adm0", 242), ("adm1", 1667), ("adm2", 3602)):
        q = BND / "display" / f"{lvl}.parquet"
        n = len(gpd.read_parquet(q)) if q.exists() else None
        print(lvl, n, "expected", want, "OK" if n == want else "DIFFERENT")
        bad += n != want
    print("\nRESULT:", "all as expected" if not bad else f"{bad} place(s) differ: send this file to CODE-PUB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
