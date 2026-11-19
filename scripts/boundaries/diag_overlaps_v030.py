"""diag_overlaps_v030.py -- read-only: where are the ADM1 overlaps that check 1 reports (v0.3.0)?

Run (from the repo root, after build_boundaries.py):
    python scripts\\boundaries\\diag_overlaps_v030.py --out-dir "D:\\GISData\\Boundaries\\out\\abf-boundaries-v0.3.0"

Reads display/adm1.parquet, writes diag_overlaps_v030.txt into --out-dir. For every pair of ADM1 units of different countries
(and, for IDN, of the same country) that overlap by more than 0.01 km2 it prints the area, the number of parts, the place
(lon, lat of the largest part) and whether the place lies inside the NE land of a third country. Nothing is changed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

import bnd_common as c  # noqa: E402

MIN_KM2 = 0.01


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()
    adm1 = gpd.read_parquet(args.out_dir / "display" / "adm1.parquet")
    tree = shapely.STRtree(adm1.geometry.values)
    ids, iso, geoms = adm1["unit_id"].values, adm1["iso3"].values, adm1.geometry.values
    rows = []
    a_idx, b_idx = tree.query(geoms, predicate="intersects")
    for i, j in zip(a_idx, b_idx):
        if j <= i:
            continue
        inter = shapely.intersection(geoms[i], geoms[j])
        if inter.is_empty or inter.area == 0:
            continue
        polys = [g for g in shapely.get_parts(inter) if g.geom_type == "Polygon" and g.area > 0]
        if not polys:
            continue
        ea = c.to_equal_area(gpd.GeoSeries(polys, crs=c.CRS_WGS84))
        areas = [g.area / 1e6 for g in ea.values]
        total = sum(areas)
        if total <= MIN_KM2:
            continue
        big = polys[max(range(len(polys)), key=lambda k: areas[k])]
        pt = big.representative_point()
        rows.append((total, ids[i], ids[j], len(polys), round(pt.x, 4), round(pt.y, 4), max(areas), iso[i] == iso[j]))
    rows.sort(key=lambda r: -r[0])
    lines = [f"{len(rows)} overlapping pairs above {MIN_KM2} km2 (equal-area EPSG:6933)",
             "area_km2 | unit_a | unit_b | parts | lon | lat (largest part) | largest_part_km2 | same_country"]
    for r in rows:
        lines.append(f"{r[0]:.4f} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]:.4f} | {r[7]}")
    non_idn = [r for r in rows if not (r[1].startswith("IDN") and r[2].startswith("IDN"))]
    lines += ["", "without pairs inside Indonesia:"] + [f"{r[0]:.4f} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]}" for r in non_idn]
    text = "\n".join(lines)
    (args.out_dir / "diag_overlaps_v030.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
