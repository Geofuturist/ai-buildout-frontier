r"""abf-dc 0.2.0: texts of [RES]7 in the yamls of the three layers of 0.1.0 (RES_texts_DC_v0_2_0 r2, sections 3, 4, 9.3). Meta only, the data do not change.

Run command (from the repository root, Windows):
    python scripts\publish\patch_dc_texts_v020.py

Changes (each only if not yet done; safe to run twice; the line endings of every file are kept):
  layers\dc_atlas_points.yaml      description: last sentence on the map by place; known_gaps item 3: last sentence; attribution_text: tail
  layers\dc_atlas_count_adm0.yaml  attribution_text: tail
  layers\dc_epoch_points.yaml      display.symbol: diamond; display.legend_layer_note
Nothing else in these files is touched. Run patch_dc_atlas_points_v020.py (-r1, display.map) separately; the order does not matter.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO_ROOT

ATTR_OLD = "their addresses and names, and counted by country. These figures are not the Atlas as published."
ATTR_NEW = "their addresses and names, and counted by country, by place and by U.S. county. These figures are not the Atlas as published."
DESC_OLD = "  Capacity is the Atlas's size class as given; where the Atlas gives none, it is shown as unknown, not\n  estimated.\nfields:"
DESC_NEW = ("  Capacity is the Atlas's size class as given; where the Atlas gives none, it is shown as unknown, not\n"
            "  estimated. On the project map the records are shown by place (dc_atlas_count_places).\nfields:")
GAP_OLD = "(37.1%). These records are in\n    the files and in the country counts but are not drawn on the map."
GAP_NEW = ("(37.1%).\n    The 1,583 county records are counted by county in dc_atlas_count_usa_adm2, and the 2,195 records without a place only by\n"
           "    country. Neither group is drawn on the map.")
SYMBOL_LINES = ["  symbol: diamond",
                '  legend_layer_note: "AI data centers that Epoch AI selects by their AI computing capacity."']


def swap(text: str, old: str, new: str, done_marker: str, what: str, done: list[str]) -> str:
    if done_marker in text:
        return text
    if text.count(old) != 1:
        raise SystemExit(f"{what}: the expected text was found {text.count(old)} times (1 needed): edit by hand and tell CODE-PUB")
    done.append(what)
    return text.replace(old, new, 1)


def patch_points(text: str) -> tuple[str, list[str]]:
    done: list[str] = []
    text = swap(text, ATTR_OLD, ATTR_NEW, "counted by country, by place", "attribution_text", done)
    text = swap(text, DESC_OLD, DESC_NEW, "shown by place (dc_atlas_count_places)", "description", done)
    text = swap(text, GAP_OLD, GAP_NEW, "counted by county in dc_atlas_count_usa_adm2", "known_gaps item 3", done)
    return text, done


def patch_adm0(text: str) -> tuple[str, list[str]]:
    done: list[str] = []
    return swap(text, ATTR_OLD, ATTR_NEW, "counted by country, by place", "attribution_text", done), done


def patch_epoch(text: str) -> tuple[str, list[str]]:
    done: list[str] = []
    lines = text.split("\n")
    try:
        d = lines.index("display:")
    except ValueError:
        raise SystemExit("epoch: block 'display:' not found") from None
    end = d + 1
    while end < len(lines) and (lines[end].startswith(" ") or lines[end] == ""):
        end += 1
    block = lines[d + 1:end]
    if any(l.startswith("  symbol:") for l in block):
        return text, done
    g = next((i for i, l in enumerate(block) if l.startswith("  geometry_type:")), None)
    if g is None:
        raise SystemExit("epoch: display.geometry_type not found")
    lines[d + 1 + g + 1:d + 1 + g + 1] = SYMBOL_LINES
    done.append("display.symbol and legend_layer_note")
    return "\n".join(lines), done


FILES = [("dc_atlas_points.yaml", patch_points), ("dc_atlas_count_adm0.yaml", patch_adm0), ("dc_epoch_points.yaml", patch_epoch)]


def main() -> int:
    n = 0
    for name, fn in FILES:
        path = REPO_ROOT / "layers" / name
        raw = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in raw else "\n"
        new, done = fn(raw.replace("\r\n", "\n"))
        if done:
            path.write_bytes(new.replace("\n", eol).encode("utf-8"))
            print(f"changed layers\\{name}:", "; ".join(done))
            n += 1
        else:
            print(f"layers\\{name}: already done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
