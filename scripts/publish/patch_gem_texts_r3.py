r"""abf-energy 0.1.0: texts of [RES]7 r3 (RES_texts_GEM_v0_1_0 r3, section 3 known_gaps) in layers\energy_plants_gem_locations.yaml. Meta only, the data do not change.

Run command (from the repository root, Windows):
    python scripts\publish\patch_gem_texts_r3.py

Changes (each only if not yet done; safe to run twice; the line endings of the file are kept):
  known_gaps item on approximate points: the last sentence ("labeled as approximate" is no longer true: the map does not set these points apart)
  known_gaps: a new item on approximate points shared by many plants

The numbers of the new item are counted here, from data\gem\energy_plants_gem_locations.csv (the release file is a byte copy of it):
points with the same lon and lat among the rows, number of different location_id on each point, points with 20 or more plants.
The counted numbers go into the text. Where they differ from the numbers of [RES]7, the difference is printed: tell CODE-PUB.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO_ROOT

LAYER = Path("layers") / "energy_plants_gem_locations.yaml"
CSV = Path("data") / "gem" / "energy_plants_gem_locations.csv"
MIN_PLANTS = 20
# numbers of RES_texts_GEM r3 (control values; the counted ones are published)
RES_VALUES = {"points": 134, "plants": 5199, "china": 3941, "largest": 165, "largest_lon": 120.0, "largest_lat": 33.0}

APPROX_OLD = re.compile(r"  - 67,148 of the 138,504 rows \(48\.5%\).*?(?=\n  - Units of one plant)", re.S)
APPROX_DONE = "The map does not set these points apart"
SHARED_DONE = "Many approximate points are shared by several plants."
APPROX_TEXT = ("67,148 of the 138,504 rows (48.5%) take their point from a unit whose location GEM gives as approximate, "
               "based on “using nearest city or other information in research”. The map does not set these points apart; "
               "the plant window says which they are.")


def shared_points(df: pd.DataFrame) -> dict:
    """Points shared by MIN_PLANTS or more different GEM plants, among the rows of the plant layer."""
    key = df["lon"] + "," + df["lat"]
    per_point = df.groupby(key)["location_id"].nunique()
    big = per_point[per_point >= MIN_PLANTS]
    rows = df[key.isin(big.index)]
    top = big.idxmax()
    lon, lat = (float(v) for v in top.split(","))
    top_rows = df[key == top]
    places = top_rows.loc[top_rows["subnational_unit"] != "", "subnational_unit"]
    return {
        "points": len(big),
        "plants": int(rows["location_id"].nunique()),
        "china": int(rows.loc[rows["iso3_source"] == "CHN", "location_id"].nunique()),
        "largest": int(big.max()),
        "largest_lon": lon,
        "largest_lat": lat,
        "place": places.mode().iloc[0] if len(places) else "",
        "all_approximate": bool((rows["coord_precision"] == "approximate").all()),
    }


def deg(value: float, pos: str, neg: str) -> str:
    return f"{abs(value):g}°{pos if value >= 0 else neg}"


def shared_text(s: dict) -> str:
    place = f" in {s['place']}" if s["place"] else ""
    return (f"Many approximate points are shared by several plants. {s['points']} points carry {MIN_PLANTS} or more different "
            f"GEM plants each, {s['plants']:,} plants in all, {s['china']:,} of them in China; the largest, at "
            f"{deg(s['largest_lon'], 'E', 'W')}, {deg(s['largest_lat'], 'N', 'S')}{place}, carries {s['largest']}. "
            f"Such a point is GEM's approximate location, not the site of any of these plants.")


def item(text: str) -> str:
    """One known_gaps item in the style of the file: '  - ...' with the continuation lines indented by 4."""
    dumped = yaml.safe_dump([text], width=118, allow_unicode=True, default_flow_style=False).rstrip("\n")
    return "\n".join("  " + line for line in dumped.split("\n"))


def patch_text(text: str, stats: dict) -> tuple[str, list[str]]:
    """text uses LF only. Returns the new text and the list of what was changed."""
    done: list[str] = []
    if APPROX_DONE not in text:
        if len(APPROX_OLD.findall(text)) != 1:
            raise SystemExit("known_gaps: the item on approximate points was not found exactly once: edit by hand and tell CODE-PUB")
        text = APPROX_OLD.sub(lambda m: item(APPROX_TEXT), text, count=1)
        done.append("known_gaps: approximate points")
    if SHARED_DONE not in text:
        anchor = "\n  - Units of one plant can have different points."
        if text.count(anchor) != 1:
            raise SystemExit("known_gaps: the item on units of one plant was not found exactly once: edit by hand and tell CODE-PUB")
        text = text.replace(anchor, "\n" + item(shared_text(stats)) + anchor, 1)
        done.append("known_gaps: shared points")
    return text, done


def main() -> int:
    csv_path, layer_path = REPO_ROOT / CSV, REPO_ROOT / LAYER
    for p in (csv_path, layer_path):
        if not p.exists():
            raise SystemExit(f"not found: {p} (run from the repository root, on the branch gem-pub-v010)")
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    stats = shared_points(df)
    print(f"counted from {CSV}: {stats['points']} points with {MIN_PLANTS}+ plants, {stats['plants']:,} plants, "
          f"{stats['china']:,} in China, the largest {stats['largest']} at {stats['largest_lon']:g}, {stats['largest_lat']:g} ({stats['place'] or 'no region'})")
    if not stats["all_approximate"]:
        print("WARNING: some of these points are not approximate: the text says 'approximate points'. Tell CODE-PUB.")
    for k, v in RES_VALUES.items():
        if stats[k] != v:
            print(f"DIFFERENCE: {k}: counted {stats[k]}, in RES_texts_GEM r3 {v}. The counted number is published. Tell CODE-PUB.")
    raw = layer_path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    new, done = patch_text(raw.replace("\r\n", "\n"), stats)
    yaml.safe_load(new)  # the result must stay valid yaml
    if not done:
        print("nothing to change: the texts are already in place")
        return 0
    layer_path.write_bytes((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    print(f"changed {LAYER}: " + "; ".join(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
