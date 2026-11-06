r"""abf-energync 0.1.0: the address of TransitionZero's terms of use in the two TZ layer yamls.

The pre-flight of [CODE-GEM] had the address of a preview site (transition-zero.vercel.app). V saved the real page
(canonical address https://www.transitionzero.org/terms/tz-sam-terms-of-use, retrieved 2026-10-31 for the data, page saved
2026-11-06); the page states CC BY-NC 4.0, attribution to TransitionZero, a statement of changes, the logo on visual content.

Run command (from the repository root, Windows):
    python scripts\publish\patch_gem_final_r1.py

Changes `url:` and `evidence_url:` of the source transitionzero_tzsam_aug2025 in
layers\energy_plants_gem_tzsam_units.yaml and layers\energy_plants_gem_tzsam_locations.yaml.
Safe to run twice; the line endings of the files are kept.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from common import REPO_ROOT  # noqa: E402

OLD = "https://transition-zero.vercel.app/terms/tz-sam-terms-of-use"
NEW = "https://www.transitionzero.org/terms/tz-sam-terms-of-use"
FILES = [Path("layers") / "energy_plants_gem_tzsam_units.yaml", Path("layers") / "energy_plants_gem_tzsam_locations.yaml"]


def main() -> int:
    rc = 0
    for rel in FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"STOP: not found: {path} (run from the repository root, on the branch gem-pub-v010)")
            return 2
        raw = path.read_bytes().decode("utf-8")
        n = raw.count(OLD)
        if n == 0:
            print(f"nothing to change in {rel}" + (" (new address already there)" if NEW in raw else " (address not found: tell CODE-PUB)"))
            rc = rc or (0 if NEW in raw else 1)
            continue
        new = raw.replace(OLD, NEW)
        yaml.safe_load(new)
        path.write_bytes(new.encode("utf-8"))
        print(f"changed {rel}: {n} address(es)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
