r"""abf-energy 0.1.0: texts of [RES]7 r4 (RES_texts_GEM_v0_1_0 r4, sections 2 and 3) in the two layer yamls of abf-energy.
Meta only, the data do not change. The numbers were counted by CODE-PUB from the release files (check_gem_numbers, 04.11.2026).

Run command (from the repository root, Windows):
    python scripts\publish\patch_gem_texts_r4.py

Changes (each only if not yet done; safe to run twice; the line endings of the files are kept):
  energy_plants_gem_units.yaml, known_gaps: points of one plant: 399 plants (latitudes or longitudes more than 1 degree apart);
                                            country: Crimea, 34 units, 31 of them in the area of disputed control
  energy_plants_gem_locations.yaml, known_gaps: shared points: "5,198 different plants";
                                                points of one plant: 399 plants;
                                                country: Crimea, 23 rows, 20 of them in the area of disputed control, 3 without control_iso3
Each item is found by its first words and replaced as a whole.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from common import REPO_ROOT  # noqa: E402

UNITS = Path("layers") / "energy_plants_gem_units.yaml"
LOCATIONS = Path("layers") / "energy_plants_gem_locations.yaml"

# (file, first words of the item, new text, label)
ITEMS = [
    (UNITS, "GEM gives an approximate location for 73,268",
     "GEM gives an approximate location for 73,268 of the 164,672 units (44.5%), which GEM bases on “using nearest city or "
     "other information in research”. Units of one plant can have different points: for 399 GEM plants, the latitudes or "
     "longitudes of their units differ by more than 1°. Some of these may be errors in the source. The project does not "
     "correct points.",
     "points of one plant: 399"),
    (UNITS, "The country is given twice:",
     "The country is given twice: by GEM's country table (iso3_gem, iso3_source) and by the point (iso3_frame). 4,609 units "
     "lie outside the generalized 1:10 million country outlines but within 22.2 km of a country, and get the nearest one; "
     "858 units lie farther out, most of them offshore wind, and have no iso3_frame. For 291 units the point lies in another "
     "country of the frame than the one GEM names. Some of them lie near borders, where generalized outlines can put a point "
     "across the line; others lie in areas that GEM and the frame assign differently, such as Crimea: 34 units that GEM lists "
     "under Ukraine lie in Crimea or just off its coast, which the frame shows under Russian control; 31 of them lie inside "
     "the area of disputed control and carry control_iso3. Neither is a position of the project.",
     "country: Crimea 34 / 31"),
    (LOCATIONS, "Many approximate points are shared by several plants.",
     "Many approximate points are shared by several plants. 134 points carry 20 or more different GEM plants each, 5,198 "
     "different plants in all, 3,941 of them in China; the largest, at 120°E, 33°N in Jiangsu, carries 165. Such a point is "
     "GEM's approximate location, not the site of any of these plants.",
     "shared points: 5,198 different plants"),
    (LOCATIONS, "Units of one plant can have different points.",
     "Units of one plant can have different points. Where they are more than 1 km apart, the rows are kept apart rather than "
     "averaged. For 399 GEM plants the latitudes or longitudes of the units differ by more than 1°; some of these may be "
     "errors in the source, which the project does not correct.",
     "points of one plant: 399"),
    (LOCATIONS, "The country is given by GEM's table and by the point.",
     "The country is given by GEM's table and by the point. 3,256 rows lie outside the generalized country outlines but "
     "within 22.2 km of a country and get the nearest one. For 233 rows the point lies in another country of the frame than "
     "the one GEM names, among them 23 rows in Crimea or just off its coast (Ukraine in GEM; Russia in the frame). 20 of "
     "them lie inside the area of disputed control, where the frame records Ukraine's claim (control_iso3); 3 offshore wind "
     "farms share one approximate point at sea and get Russia by the 22.2 km rule without control_iso3. Neither is a "
     "position of the project.",
     "country: Crimea 23 / 20 / 3"),
]


def item(text: str) -> str:
    """One known_gaps item in the style of the file: '  - ...' with the continuation lines indented by 4."""
    dumped = yaml.safe_dump([text], width=118, allow_unicode=True, default_flow_style=False).rstrip("\n")
    return "\n".join("  " + line for line in dumped.split("\n"))


def find_item(lines: list[str], anchor: str) -> tuple[int, int]:
    """Lines [start, end) of the known_gaps item whose text begins with anchor; SystemExit if not exactly one."""
    starts = [i for i, ln in enumerate(lines) if re.match(r"^  - ['\"]?" + re.escape(anchor), ln)]
    if len(starts) != 1:
        raise SystemExit(f"the item '{anchor}' was found {len(starts)} times (needs exactly once): edit by hand and tell CODE-PUB")
    end = starts[0] + 1
    while end < len(lines) and re.match(r"^    \S|^\s*$", lines[end]) and not re.match(r"^  - ", lines[end]):
        end += 1
    return starts[0], end


def main() -> int:
    for rel in (UNITS, LOCATIONS):
        if not (REPO_ROOT / rel).exists():
            print(f"STOP: not found: {REPO_ROOT / rel} (run from the repository root, on the branch gem-pub-v010)")
            return 2
    for rel in (UNITS, LOCATIONS):
        path = REPO_ROOT / rel
        raw = path.read_bytes().decode("utf-8")
        crlf = "\r\n" in raw
        lines = raw.replace("\r\n", "\n").split("\n")
        done: list[str] = []
        for f, anchor, text, label in ITEMS:
            if f != rel:
                continue
            a, b = find_item(lines, anchor)
            block = "\n".join(lines[a:b])
            if yaml.safe_load(block)[0].split() == text.split():
                continue
            lines[a:b] = item(text).split("\n")
            done.append(label)
        if not done:
            print(f"nothing to change in {rel}: the texts are already in place")
            continue
        new = "\n".join(lines)
        yaml.safe_load(new)  # the result must stay valid yaml
        path.write_bytes((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
        print(f"changed {rel}: " + "; ".join(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
