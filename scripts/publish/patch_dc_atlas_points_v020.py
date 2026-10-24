r"""abf-dc 0.2.0: two small changes in layers\dc_atlas_points.yaml, nothing else in the file is touched.

Run command (from the repository root, Windows):
    python scripts\publish\patch_dc_atlas_points_v020.py

Changes (SPEC_DC_world_v0_2_0 r1, section 3 items 4 and 5, section 1 item 7). Safe to run twice.
  tiles.extra_args    "-r1" first: the tippecanoe default thins points at the low zooms (the 0.1.0 defect: 1,097 of 6,087 points at z8)
  display.map: false  the Atlas points are shown by the layer dc_atlas_count_places, not on their own
The file keeps its line endings. The texts of [RES] (known_gaps, legend) are not touched here.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO_ROOT

OLD_ARGS = 'extra_args: ["--drop-densest-as-needed", "--extend-zooms-if-still-dropping"]'
NEW_ARGS = 'extra_args: ["-r1", "--drop-densest-as-needed", "--extend-zooms-if-still-dropping"]'
MAP_LINE = "  map: false   # SPEC_DC_world_v0_2_0 section 1 item 7: shown by dc_atlas_count_places"


def patch_text(text: str) -> tuple[str, list[str]]:
    """Return (new text with LF line ends, list of done changes). Raises SystemExit if a place is not found."""
    done: list[str] = []
    if '"-r1"' in text.split("tiles:", 1)[-1]:
        pass
    elif OLD_ARGS in text:
        text = text.replace(OLD_ARGS, NEW_ARGS, 1)
        done.append('tiles.extra_args: "-r1" first')
    else:
        raise SystemExit("tiles.extra_args of the expected form was not found (and no -r1 yet): edit by hand and tell CODE-PUB")
    lines = text.split("\n")
    try:
        d = lines.index("display:")
    except ValueError:
        raise SystemExit("block 'display:' not found") from None
    end = d + 1
    while end < len(lines) and (lines[end].startswith(" ") or lines[end] == ""):
        end += 1
    block = lines[d + 1:end]
    if not any(l.startswith("  map:") for l in block):
        g = next((i for i, l in enumerate(block) if l.startswith("  geometry_type:")), None)
        if g is None:
            raise SystemExit("display.geometry_type not found")
        lines.insert(d + 1 + g + 1, MAP_LINE)
        done.append("display.map: false")
    return "\n".join(lines), done


def main() -> int:
    path = REPO_ROOT / "layers" / "dc_atlas_points.yaml"
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    new, done = patch_text(raw.replace("\r\n", "\n"))
    if not done:
        print("nothing to do: layers\\dc_atlas_points.yaml already has both changes")
        return 0
    path.write_bytes(new.replace("\n", eol).encode("utf-8"))
    print("changed layers\\dc_atlas_points.yaml:", "; ".join(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
