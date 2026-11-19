"""diag_outside_adm0_v030.py -- read-only: parts of each national ADM1 country that lie OUTSIDE its own ADM0 (ARCH7 D3, SPEC r5 3g p.8).

Run (from the repo root, after build_boundaries.py):
    python scripts\\boundaries\\diag_outside_adm0_v030.py --out-dir "D:\\GISData\\Boundaries\\out\\abf-boundaries-v0.3.0"

Reads display/adm0.parquet, display/adm1.parquet and boundaries/national_sources_v030.csv (the list of countries), writes
diag_outside_adm0_v030.txt and diag_outside_adm0_v030.json into --out-dir. Nothing is changed or cut.

For every national country: the parts of its units outside its own ADM0, grouped into clusters (parts closer than 0.3 deg):
centre, area, distance to the own ADM0, the units they belong to, the foreign ADM0 and foreign ADM1 they intersect.
Then, separately, the areas named by ARCH7: Hoang Sa (VNM), Dokdo/Tokto (KOR), Diaoyutai/Senkaku (TWN), Pratas (TWN), Kalayaan and
Scarborough (PHL), Serranilla, Bajo Nuevo, Quitasueno (COL) -- and the Spratly group for VNM and TWN: how much of the box is
covered by the units of the claimant, by which units, by which ADM0 of whom, and (Pratas) whether what lies outside the ADM0 is
the lagoon of the atoll.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import shapely.ops  # noqa: E402
from pyproj import Geod  # noqa: E402

import bnd_common as c  # noqa: E402
import bnd_national as bn  # noqa: E402

MIN_PART_KM2 = 0.01
CLUSTER_DEG = 0.3
GEOD = Geod(ellps="WGS84")

# name, claimant ISO3 list, lon_min, lat_min, lon_max, lat_max (approximate boxes around the feature)
NAMED = [
    ("Hoang Sa (Paracel Islands)", ["VNM"], 111.0, 15.7, 113.0, 17.2),
    ("Dokdo / Tokto", ["KOR"], 131.80, 37.20, 131.95, 37.30),
    ("Diaoyutai / Senkaku", ["TWN"], 123.4, 25.6, 124.1, 26.0),
    ("Pratas (Dongsha)", ["TWN"], 116.5, 20.55, 117.0, 20.95),
    ("Kalayaan / Spratly group", ["PHL", "VNM", "TWN"], 111.0, 7.5, 117.5, 12.2),
    ("Scarborough Shoal", ["PHL"], 117.7, 15.05, 118.0, 15.30),
    ("Serranilla Bank", ["COL"], -80.2, 15.6, -79.6, 16.1),
    ("Bajo Nuevo", ["COL"], -79.1, 15.6, -78.5, 16.1),
    ("Quitasueno", ["COL"], -81.5, 13.4, -81.0, 14.1),
]


def geodesic_km(a, b) -> float:
    return GEOD.inv(a.x, a.y, b.x, b.y)[2] / 1000.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--boundaries-dir", default=Path("boundaries"), type=Path)
    args = ap.parse_args()
    adm0 = gpd.read_parquet(args.out_dir / "display" / "adm0.parquet")
    adm1 = gpd.read_parquet(args.out_dir / "display" / "adm1.parquet")
    table = bn.load_table(args.boundaries_dir / "national_sources_v030.csv")
    isos = [i for i in table["iso3"].drop_duplicates() if i in set(adm1["iso3"])]
    a0 = dict(zip(adm0["unit_id"], adm0.geometry))
    lines: list[str] = []
    out: dict = {"countries": {}, "named": []}

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    say("# parts of the national ADM1 outside the own ADM0 (read-only; nothing is cut)")
    say(f"parts smaller than {MIN_PART_KM2} km2 are ignored; clusters = parts closer than {CLUSTER_DEG} deg")
    for iso3 in isos:
        own = a0[iso3]
        units = adm1[adm1["iso3"] == iso3]
        shapely.prepare(own)
        parts, owner = [], []
        for uid, g in zip(units["unit_id"], units.geometry):
            d = shapely.difference(g, own)
            for p in c.explode_parts(d):
                if p.geom_type == "Polygon" and p.area > 0 and c.area_km2(p) >= MIN_PART_KM2:
                    parts.append(p)
                    owner.append(uid)
        total = sum(c.area_km2(p) for p in parts)
        say(f"\n## {iso3}: {len(parts)} part(s) outside the own ADM0, {total:.1f} km2 in total")
        if not parts:
            out["countries"][iso3] = {"n_parts": 0, "area_km2": 0.0, "clusters": []}
            continue
        grown = shapely.union_all([shapely.buffer(p, CLUSTER_DEG / 2) for p in parts])
        comps = list(shapely.get_parts(grown))
        tree = shapely.STRtree(parts)
        clusters = []
        for comp in comps:
            idx = [int(i) for i in tree.query(comp, predicate="intersects")]
            ps = [parts[i] for i in idx]
            geom = shapely.union_all(ps)
            area = sum(c.area_km2(p) for p in ps)
            ctr = geom.centroid
            near = shapely.ops.nearest_points(geom, own)
            dist = geodesic_km(near[0], near[1])
            by_unit: dict[str, float] = {}
            for i in idx:
                by_unit[owner[i]] = by_unit.get(owner[i], 0.0) + c.area_km2(parts[i])
            f0 = {}
            for k, g in a0.items():
                if k != iso3 and shapely.intersects(geom, g):
                    ar = c.area_km2(shapely.intersection(geom, g))
                    if ar > 0.001:
                        f0[k] = round(ar, 3)
            other = adm1[adm1["iso3"] != iso3]
            f1 = {}
            for j in shapely.STRtree(other.geometry.values).query(geom, predicate="intersects"):
                ar = c.area_km2(shapely.intersection(geom, other.geometry.values[j]))
                if ar > 0.001:
                    f1[other["unit_id"].iloc[j]] = round(ar, 3)
            clusters.append(dict(lon=round(ctr.x, 3), lat=round(ctr.y, 3), area_km2=round(area, 2), n_parts=len(ps),
                                 distance_to_own_adm0_km=round(dist, 1), units={k: round(v, 2) for k, v in by_unit.items()},
                                 foreign_adm0=f0, foreign_adm1=dict(sorted(f1.items(), key=lambda kv: -kv[1])[:8]),
                                 bounds=[round(x, 3) for x in geom.bounds]))
        clusters.sort(key=lambda x: -x["area_km2"])
        out["countries"][iso3] = {"n_parts": len(parts), "area_km2": round(total, 1), "n_clusters": len(clusters), "clusters": clusters}
        say(f"{len(clusters)} cluster(s); largest first (up to 25 shown here, all in the json)")
        for k in clusters[:25]:
            say(f"  centre ({k['lon']}, {k['lat']}) | {k['area_km2']} km2 | {k['n_parts']} part(s) | {k['distance_to_own_adm0_km']} km from own ADM0 | "
                f"units {k['units']} | foreign ADM0 {k['foreign_adm0'] or '-'} | foreign ADM1 {k['foreign_adm1'] or '-'}")

    say("\n# named areas (approximate boxes; ARCH7 D3)")
    all_units = adm1
    for name, claimants, x0, y0, x1, y1 in NAMED:
        box = shapely.box(x0, y0, x1, y1)
        centre = box.centroid
        box_km2 = c.area_km2(box)
        row = dict(name=name, box=[x0, y0, x1, y1], box_km2=round(box_km2, 1), claimants={})
        say(f"\n## {name}  (box {x0}..{x1} E, {y0}..{y1} N, {box_km2:.0f} km2)")
        covering = [k for k, g in a0.items() if shapely.contains(g, centre)]
        say(f"  ADM0 polygon covering the centre of the box: {covering or 'none'}")
        row["adm0_covering_centre"] = covering
        # who else's units / ADM0 meet the box
        meet0 = {k: round(c.area_km2(shapely.intersection(g, box)), 2) for k, g in a0.items() if shapely.intersects(g, box)}
        say(f"  ADM0 areas inside the box (km2): {meet0 or 'none'}")
        row["adm0_in_box_km2"] = meet0
        for iso3 in claimants:
            if iso3 not in isos:
                continue
            us = all_units[all_units["iso3"] == iso3]
            per_unit = {}
            for uid, g in zip(us["unit_id"], us.geometry):
                if shapely.intersects(g, box):
                    inter = shapely.intersection(g, box)
                    in_own = shapely.intersection(inter, a0[iso3])
                    per_unit[uid] = dict(unit_km2_in_box=round(c.area_km2(inter), 2), inside_own_adm0_km2=round(c.area_km2(in_own), 2),
                                         outside_own_adm0_km2=round(c.area_km2(inter) - c.area_km2(in_own), 2))
            own_in_box = c.area_km2(shapely.intersection(a0[iso3], box))
            say(f"  {iso3}: own ADM0 in the box {own_in_box:.2f} km2; units meeting the box: {per_unit or 'none'}")
            row["claimants"][iso3] = dict(own_adm0_in_box_km2=round(own_in_box, 2), units=per_unit)
        if name.startswith("Pratas"):
            u = row["claimants"].get("TWN", {})
            out_km2 = sum(v["outside_own_adm0_km2"] for v in u.get("units", {}).values())
            in_km2 = sum(v["inside_own_adm0_km2"] for v in u.get("units", {}).values())
            verdict = ("the unit polygon is much larger than the ADM0 land of the atoll: what lies outside the ADM0 is the lagoon / reef "
                       "water of the atoll" if out_km2 > in_km2 else "the unit polygon is not larger than the ADM0 inside the box")
            say(f"  Pratas check: inside own ADM0 {in_km2:.2f} km2, outside own ADM0 {out_km2:.2f} km2 -> {verdict} (a judgement by area only; "
                f"look at the cluster in QGIS)")
            row["pratas_check"] = dict(inside_own_adm0_km2=round(in_km2, 2), outside_own_adm0_km2=round(out_km2, 2), reading=verdict)
        out["named"].append(row)
    text = "\n".join(lines)
    (args.out_dir / "diag_outside_adm0_v030.txt").write_text(text, encoding="utf-8")
    (args.out_dir / "diag_outside_adm0_v030.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nwritten {args.out_dir / 'diag_outside_adm0_v030.txt'} and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
