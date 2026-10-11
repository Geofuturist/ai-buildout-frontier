r"""Add the v0.2.0 contract fields to the layer yaml files without touching anything else in them.

Run command (from the repository root, Windows):
    python scripts\publish\patch_yaml_v020.py

Changes (SPEC_META r7, section 6 item 23). Safe to run twice: a file that already has the change is skipped.
  layers\energy_transmission_lines_hifld.yaml   coverage.iso3: [USA]
  layers\dc_icpe_georisques.yaml                coverage.iso3: [FRA]; display.value_field removed; display.home_bbox_from
  layers\energy_generation_odre_adm2.yaml       display.home_bbox_from (mainland France with Corsica)
  layers\energy_consumption_agenceore_adm2.yaml display.home_bbox_from
  layers\energy_transmission_rte_adm2.yaml      display.home_bbox_from
The text of the files is edited in place, so other edits of other people in the same files stay.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO_ROOT

HOME_BBOX = [
    "  home_bbox_from:      # SPEC_META 6 item 23: mainland France with Corsica (01-95, 2A, 2B); overseas departments stay in the data",
    "    iso3: FRA",
    "    level: ADM2",
    "    code_regex: '0[1-9]|[1-8][0-9]|9[0-5]|2A|2B'",
]


def patch(path: Path, edits: list[tuple[str, str]]) -> str:
    """edits: ('iso3', 'USA'|'FRA') | ('home_bbox', polygon|point) | ('drop_value_field', '')"""
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    done: list[str] = []
    for kind, arg in edits:
        if kind == "iso3":
            lines = text.split("\n")
            try:
                start = lines.index("coverage:")
            except ValueError:
                raise SystemExit(f"{path.name}: block 'coverage:' not found") from None
            end = start + 1
            while end < len(lines) and (lines[end].startswith(" ") or lines[end] == ""):
                end += 1
            block = lines[start + 1:end]
            if any(l.startswith("  iso3:") for l in block):
                continue
            g = next((i for i, l in enumerate(block) if l.startswith("  geography:")), None)
            if g is None:
                raise SystemExit(f"{path.name}: 'geography:' not found in the coverage block")
            g += 1
            while g < len(block) and block[g].startswith("    "):  # continuation lines of a long geography text
                g += 1
            lines.insert(start + 1 + g, f"  iso3: [{arg}]")
            text = "\n".join(lines)
            done.append("iso3")
        elif kind == "home_bbox":
            if "home_bbox_from:" in text:
                continue
            head = f"display:\n  geometry_type: {arg}\n"
            if head not in text:
                raise SystemExit(f"{path.name}: expected '{head.strip()}' at the start of the display block")
            text = text.replace(head, head + "\n".join(HOME_BBOX) + "\n", 1)
            done.append("home_bbox_from")
        elif kind == "drop_value_field":
            new, n = re.subn(r"(^display:\n(?:  [^\n]*\n)*?)  value_field:[^\n]*\n", r"\1", text, count=1, flags=re.M)
            if n:
                text = new
                done.append("value_field removed")
    if done:
        path.write_bytes(text.replace("\n", eol).encode("utf-8"))
    return ", ".join(done) if done else "already done"


def main() -> int:
    layers = REPO_ROOT / "layers"
    plan = {
        "energy_transmission_lines_hifld.yaml": [("iso3", "USA")],
        "dc_icpe_georisques.yaml": [("iso3", "FRA"), ("drop_value_field", ""), ("home_bbox", "point")],
        "energy_generation_odre_adm2.yaml": [("home_bbox", "polygon")],
        "energy_consumption_agenceore_adm2.yaml": [("home_bbox", "polygon")],
        "energy_transmission_rte_adm2.yaml": [("home_bbox", "polygon")],
    }
    for name, edits in plan.items():
        print(f"{name}: {patch(layers / name, edits)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
