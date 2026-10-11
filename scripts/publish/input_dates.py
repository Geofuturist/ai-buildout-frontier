r"""List the input files of all layers with their dates (for retrieved_at in the layer yaml files).

Run command (from the repository root, Windows):
    python scripts\publish\input_dates.py

Reads layers\*.yaml and the legacy meta files they point to, collects every file name found
there (tables, source workbooks, archives, raw downloads), finds each file on this computer
(first by the path, then by searching D:\GISData by file name) and prints:
  created  = date the file appeared on this disk (usually the download date)
  modified = date inside the file system (for a download it is often the publisher's date)
The result is also saved to research\publish\input_dates.txt. Nothing is changed.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from common import REPO_ROOT, resolve_path

SEARCH_ROOTS = [Path("D:/GISData")]
FILE_RE = re.compile(r"[\w\-. ()\\/:]+\.(csv|xlsx|xls|zip|h5|json|geojson|gpkg|shp|html|htm|parquet|txt)$", re.I)
SKIP_KEYS = {"external_html"}  # saved web pages are not data downloads


def strings(node, key=""):  # noqa: ANN001, ANN201
    """Yield (key, text) for every string in a nested yaml/json structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from strings(v, str(k))
    elif isinstance(node, list):
        for v in node:
            yield from strings(v, key)
    elif isinstance(node, str):
        yield key, node


def is_data_file(text: str) -> bool:
    """A file name or path, not a sentence; rule tables and research notes of the project are skipped."""
    low = text.lower().replace("\\", "/")
    return bool(FILE_RE.search(text)) and len(text) < 260 and not re.search(r"[;,] |\(|\)| \+ ", text) \
        and "/rules/" not in low and "/research/" not in low and not low.startswith("research/")


def find_file(text: str) -> Path | None:
    try:
        p = resolve_path(text)
        if p.exists():
            return p
    except Exception:  # noqa: BLE001
        pass
    name = re.split(r"[\\/]", text)[-1]
    for root in SEARCH_ROOTS:
        if root.exists():
            for dirpath, _dirs, files in os.walk(root):
                if name in files:
                    return Path(dirpath) / name
    return None


def fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    seen: dict[str, set[str]] = {}
    for ypath in sorted((REPO_ROOT / "layers").glob("*.yaml")):
        cfg = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        texts = [(k, t) for k, t in strings(cfg) if k not in SKIP_KEYS and is_data_file(t)]
        for _k, t in list(texts):
            if t.endswith("_meta.json"):
                lm = find_file(t)
                if lm:
                    try:
                        data = json.loads(lm.read_text(encoding="utf-8"))
                        texts += [(k2, t2) for k2, t2 in strings(data) if is_data_file(t2)]
                        snap = data.get("snapshot_date")
                        if snap:
                            seen.setdefault(f"[legacy snapshot_date {snap}] {t}", set()).add(ypath.name)
                    except (OSError, ValueError):
                        pass
        for _k, t in texts:
            seen.setdefault(t, set()).add(ypath.name)
    lines = [f"Checked {datetime.now():%Y-%m-%d %H:%M}", ""]
    for text in sorted(seen):
        used = ", ".join(sorted(seen[text]))
        if text.startswith("[legacy"):
            lines += [text, f"    used by: {used}", ""]
            continue
        p = find_file(text)
        if p is None:
            lines += [f"NOT FOUND  {text}", f"    used by: {used}", ""]
            continue
        st = p.stat()
        lines += [str(p), f"    created {fmt(st.st_ctime)}   modified {fmt(st.st_mtime)}   {st.st_size:,} bytes",
                  f"    used by: {used}", ""]
    out = REPO_ROOT / "research" / "publish" / "input_dates.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("\n".join(lines))
    print(f"Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
