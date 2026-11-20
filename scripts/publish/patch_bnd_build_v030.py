r"""Patch scripts\publish\boundaries_build.py for abf-boundaries v0.3.0 (idempotent).

Run command (from the repository root, Windows):
    python scripts\publish\patch_bnd_build_v030.py            # shows what would change, writes nothing
    python scripts\publish\patch_bnd_build_v030.py --apply    # writes the file

Two changes, nothing else:
  1. REFERENCE_DESCRIPTIONS: four new keys for the reference files of 0.3.0 (national_adm1_units, national_adm1_report,
     overlap_whitelist, diag_outside_adm0);
  2. the name of an input file in sources[].inputs[]: a "/" or "\" in the product name (Indonesia: "kabupaten/kota") is
     replaced by "-", because the schema forbids a slash in `file`.
Line endings are kept.
"""
from __future__ import annotations

import sys
from pathlib import Path

PATH = Path("scripts") / "publish" / "boundaries_build.py"

OLD1 = '''    "license_unicode": "Unicode License v3 notice for the CLDR data used: codes and English names of first-level units.",
}'''
NEW1 = '''    "license_unicode": "Unicode License v3 notice for the CLDR data used: codes and English names of first-level units.",
    # version 0.3.0 (RES_texts_BND_v0_3_0 section 5; ARCH7 19 November: overlap_whitelist and the JSON diagnostic are published)
    "national_adm1_units": ("One row for each first-level unit from a national source in version 0.3.0: the code and name in the "
                            "source, the ISO 3166-2 code, the published name and how it was chosen."),
    "national_adm1_report": "Build report of the first-level units from national sources in version 0.3.0.",
    "overlap_whitelist": "Overlaps between units of the frame that are accepted as they are, each with its reason.",
    "diag_outside_adm0": ("Parts of national first-level units that lie outside the country outline of the frame, "
                          "with their areas in km2."),
}'''
OLD2 = '''name = re.split(r"[\\\\/]", product.split(": ")[-1])[-1] if "CLDR" in product else product\n'''
NEW2 = '''name = re.split(r"[\\\\/]", product.split(": ")[-1])[-1] if "CLDR" in product else re.sub(r"\\s*[\\\\/]\\s*", "-", product)\n'''


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    if not PATH.exists():
        print(f"STOP: {PATH} not found; run from the repository root")
        return 2
    raw = PATH.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    changed: list[str] = []
    for label, old, new in (("REFERENCE_DESCRIPTIONS", OLD1, NEW1), ("input file name without a slash", OLD2, NEW2)):
        if new in text:
            continue
        if text.count(old) != 1:
            print(f"STOP: the text of {label} is not as expected ({text.count(old)} matches); the file is not changed")
            return 2
        text = text.replace(old, new)
        changed.append(label)
    if not changed:
        print("Nothing to change: the file is already patched.")
        return 0
    print("Changes:")
    for c in changed:
        print("  -", c)
    if apply:
        PATH.write_bytes(text.replace("\n", nl).encode("utf-8"))
        print(f"Written {PATH}")
    else:
        print("Not written (run again with --apply).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
