r"""Last edits of the layer yaml files before the final abf-fra v0.2.0 (ARCH 13.10). Safe to run twice.

Run command (from the repository root, Windows):
    python scripts\publish\patch_fra_v020_final.py

  layers\energy_generation_odre_adm1.yaml        display.breaks = 2000, 6000, 12000, 18000
  layers\energy_consumption_agenceore_adm1.yaml  display.breaks = 1000000, 10000000, 30000000, 50000000;
                                                 sources.agenceore_conso_region.retrieved_at = 2026-10-12
                                                 (creation date of the downloaded file, from V)
  layers\energy_transmission_rte_adm1.yaml       display.breaks = 5000, 6000, 8000, 11000
The files are edited as text; nothing else in them changes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import REPO_ROOT  # noqa: E402

BREAKS = {
    "energy_generation_odre_adm1": [2000, 6000, 12000, 18000],
    "energy_consumption_agenceore_adm1": [1000000, 10000000, 30000000, 50000000],
    "energy_transmission_rte_adm1": [5000, 6000, 8000, 11000],
}


def patch(layer_id: str) -> list[str]:
    path = REPO_ROOT / "layers" / f"{layer_id}.yaml"
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    log: list[str] = []
    # display.breaks: the block "  breaks:" followed by "  - N" lines
    bi = next((i for i, l in enumerate(lines) if l == "  breaks:"), None)
    if bi is None:
        raise SystemExit(f"STOP {layer_id}: 'breaks:' not found")
    end = bi + 1
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1
    new = ["  breaks:"] + [f"  - {v}" for v in BREAKS[layer_id]]
    if lines[bi:end] != new:
        lines[bi:end] = new
        log.append(f"  changed  display.breaks = {BREAKS[layer_id]}")
    else:
        log.append("  already  display.breaks")
    if layer_id == "energy_consumption_agenceore_adm1":
        si = next((i for i, l in enumerate(lines) if l == "- source_id: agenceore_conso_region"), None)
        if si is None:
            raise SystemExit(f"STOP {layer_id}: source agenceore_conso_region not found")
        ri = next((i for i in range(si, len(lines)) if lines[i].startswith("  retrieved_at:")), None)
        if ri is None:
            raise SystemExit(f"STOP {layer_id}: retrieved_at not found in the source")
        if lines[ri] != "  retrieved_at: '2026-10-12'":
            lines[ri] = "  retrieved_at: '2026-10-12'"
            log.append("  changed  sources.agenceore_conso_region.retrieved_at = 2026-10-12")
        else:
            log.append("  already  sources.agenceore_conso_region.retrieved_at")
    text = "\n".join(lines)
    doc = yaml.safe_load(text)
    if doc["display"]["breaks"] != BREAKS[layer_id]:
        raise SystemExit(f"STOP {layer_id}: breaks are not as intended after the edit; the file was not changed")
    if layer_id == "energy_consumption_agenceore_adm1":
        src = next(s for s in doc["sources"] if s["source_id"] == "agenceore_conso_region")
        if str(src["retrieved_at"]) != "2026-10-12":
            raise SystemExit(f"STOP {layer_id}: retrieved_at is not as intended; the file was not changed")
    if any(l.startswith("  changed") for l in log):
        path.write_bytes(text.replace("\n", eol).encode("utf-8"))
    return log


def main() -> int:
    for layer_id in BREAKS:
        print(f"== layers\\{layer_id}.yaml")
        print("\n".join(patch(layer_id)))
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
