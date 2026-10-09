#!/usr/bin/env python3
"""
make_registry_template.py -- a planning list for V, not used by build_boundaries.py.

Run (from repo root, after fetch_boundary_sources.py):
    python scripts\\boundaries\\make_registry_template.py --sources-dir "D:\\GISData\\Boundaries\\sources" --out boundaries\\boundary_registry_template.csv

For every ADM0 country (SPEC S4.1 merge rule, same as build_boundaries.py's), lists
default values (method=ne_as_is, verified=false), the raw NE ADM1 unit count for that
country, and -- when geoBoundariesOpen-meta.csv is available -- the geoBoundaries ADM1
unit count/year and whether the two counts agree. Countries where NE and geoBoundaries
agree are the cheapest to verify next (SPEC S5.9): a matching count is not a
verification by itself, but it narrows down where to start.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bnd_common as c  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources-dir", required=True, type=Path)
    ap.add_argument("--boundaries-dir", default=Path("boundaries"), type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    import json

    manifest = json.loads((args.sources_dir / "sources_manifest.json").read_text(encoding="utf-8"))
    ne_adm0 = gpd.read_file(manifest["ne_adm0_usa"]["path"])
    ne_adm1 = gpd.read_file(manifest["ne_adm1"]["path"])
    overrides = c.load_adm0_overrides(args.boundaries_dir / "adm0_overrides.csv")

    # Display name per iso3, for the human reading this CSV -- not used by the build.
    # A few iso3 codes are shared by more than one raw NE object: the "main" country
    # (ADM0_A3 == iso3, e.g. GBR/GBR "United Kingdom") plus an override row for a
    # dependency merged into it (e.g. ESB "Dhekelia" -> GBR, WSB "Akrotiri" -> GBR,
    # USG "Guantanamo Bay USNB" -> CUB). Pass 1 takes the main country's own name
    # wherever it exists; pass 2 fills in the remaining iso3s (XKX, BRT, PGA, SCR)
    # that only exist as an override, in whatever order they come.
    iso3_by_row = []
    names = {}
    for _, row in ne_adm0.iterrows():
        iso3, _status = c.compute_iso3(row["ISO_A3_EH"], row["ADM0_A3"], overrides)
        iso3_by_row.append(iso3)
        if row["ADM0_A3"] == iso3:
            names[iso3] = row["NAME"]
    for iso3, row_name in zip(iso3_by_row, ne_adm0["NAME"]):
        names.setdefault(iso3, row_name)
    iso3s = sorted(set(iso3_by_row))

    ne_counts = ne_adm1.groupby("adm0_a3").size().to_dict()

    gb_path = manifest.get("geoboundaries_meta", {}).get("path")
    gb_adm1 = None
    if gb_path and Path(gb_path).exists():
        gb = pd.read_csv(gb_path)
        # A few ISO3 codes have more than one ADM1 row in this metadata file (e.g. IND:
        # one row with admUnitCount=1, one with 36 -- looks like a stray placeholder
        # entry alongside the real one). Keep the largest admUnitCount per ISO3 -- the
        # more-disaggregated entry is the meaningful one -- so the lookup below always
        # finds a single row.
        gb_adm1 = (
            gb[gb["boundaryType"] == "ADM1"]
            .sort_values("admUnitCount")
            .drop_duplicates("boundaryISO", keep="last")
            .set_index("boundaryISO")
        )

    rows = []
    for iso3 in iso3s:
        ne_units = ne_counts.get(iso3)  # None if this iso3 doesn't correspond to a raw NE adm0_a3 (merged/override case)
        gb_units = gb_year = counts_agree = None
        if gb_adm1 is not None and iso3 in gb_adm1.index:
            gb_row = gb_adm1.loc[iso3]
            gb_units = int(gb_row["admUnitCount"]) if not pd.isna(gb_row["admUnitCount"]) else None
            gb_year = gb_row["boundaryYearRepresented"]
            if ne_units is not None and gb_units is not None:
                counts_agree = (ne_units == gb_units)
        rows.append(dict(
            iso3=iso3, name=names.get(iso3, ""), level="ADM1", method="ne_as_is",
            verified="false", ne_adm1_units=ne_units, gb_adm1_units=gb_units,
            gb_year=gb_year, counts_agree=counts_agree,
        ))

    df = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    n_agree = int(df["counts_agree"].sum()) if "counts_agree" in df else 0
    print(f"[make_registry_template] wrote {args.out} -- {len(df)} countries, "
          f"{n_agree} with NE/geoBoundaries ADM1 counts in agreement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
