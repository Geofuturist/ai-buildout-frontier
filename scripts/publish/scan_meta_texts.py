r"""Scan the built meta.json files of a release for words and patterns that must not be in public texts.

Run command (from the repository root, Windows):
    python scripts\publish\scan_meta_texts.py "D:\GISData\release\abf-layers-v0.1.0" "D:\GISData\release\abf-boundaries-v0.1.0"

Looks for: British spelling (licence, kilometre), [RES], {placeholders} outside citation templates,
"0 more", and the wrong spellings "License Ouverte" / "Open License" / "open_license".
The names "Licence Ouverte" / "Open Licence", the code open_licence and script names (script:06_licences.py) are allowed. Nothing is changed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOWED = re.compile(r"open_licence|Licence\s+Ouverte|Open\s+Licence|https?://\S+|script:\S+", re.I)  # names, the code, URLs and script names may keep the British spelling
CHECKS = [
    ("licence (British spelling)", re.compile(r"licen[c]e", re.I), True),
    ("kilometre", re.compile(r"kilomet(re|res)\b", re.I), False),
    ("[RES] marker", re.compile(r"\[RES\]"), False),
    ("'0 more'", re.compile(r"\b0 more\b"), False),
    ("wrong 'License Ouverte'", re.compile(r"License\s+Ouverte"), False),
    ("wrong 'Open License'", re.compile(r"Open\s+License"), False),
    ("wrong 'open_license'", re.compile(r"open_license"), False),
]
PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def walk(node, path=""):  # noqa: ANN001, ANN201
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    total = 0
    for folder in argv[1:]:
        for f in sorted(Path(folder).glob("*.meta.json")):
            meta = json.loads(f.read_text(encoding="utf-8"))
            for path, text in walk(meta):
                flat = " ".join(text.split())
                cleaned = ALLOWED.sub("", flat)
                for label, rx, use_cleaned in CHECKS:
                    if rx.search(cleaned if use_cleaned else flat):
                        print(f"FOUND {label}: {f.name} {path}: ...{flat[:120]}...")
                        total += 1
                if "citation" not in path and PLACEHOLDER.search(flat):
                    print(f"FOUND placeholder: {f.name} {path}: ...{flat[:120]}...")
                    total += 1
            print(f"checked {f.name}")
    print(f"\nProblems found: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
