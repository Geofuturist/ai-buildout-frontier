r"""Shared helpers for the France layers (SPEC_FRA_layers_v0_1 r4). Not run on its own.

- the frame: the 101 FRA-2-* units of abf-boundaries-v0.1.0 (SPEC_FRA §2);
- INSEE department codes as strings (01..95, 2A, 2B, 971..976);
- one writer for every ADM2 layer: CSV + meta.json + a short markdown report, columns in the
  SPEC_META §4.1 order (unit_id, name, coverage_status, coverage_note, values...).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\GISData\Energy\France")
ADM2 = Path(r"D:\GISData\Boundaries\out\abf-boundaries-v0.1.0\display\adm2.parquet")
REPO = Path.cwd()
OUT = REPO / "data" / "fra"
RES = REPO / "research" / "fra"
# rule tables kept in git (SPEC_FRA r5 §6 p.4, P5): the build must be reproducible from the repo
RULES = OUT / "rules"
# never published (SPEC_FRA r4 §5): local only, outside the repo
PRIVATE = ROOT / "derived"


def rules_file(name: str) -> Path:
    """A rule table from data\\fra\\rules\\; stops if missing (an empty rule set must not pass silently)."""
    p = RULES / name
    if not p.exists():
        old = RES / name
        hint = f" Старая копия лежит в {old} — перенесите её в {RULES}." if old.exists() else ""
        raise SystemExit(f"СТОП: нет таблицы правил {p}.{hint}")
    return p


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_entry(p: Path) -> dict:
    return {"file": p.name, "path": str(p), "bytes": p.stat().st_size, "sha256": sha256(p)}


def dept_code(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    t = re.sub(r"\.0+$", "", str(v).strip().upper())
    if t in ("", "NAN", "NONE", "NULL"):
        return None
    if t in ("2A", "2B"):
        return t
    if t.isdigit():
        return t.zfill(2) if len(t) <= 2 else t
    return t


def load_frame(geometry: bool = False):
    """The 101 French departments: unit_id, code, name (+ geometry if asked)."""
    import geopandas as gpd
    g = gpd.read_parquet(ADM2)
    g = g[g["unit_id"].astype(str).str.startswith("FRA-2-")].copy()
    g["code"] = g["unit_id"].str.replace("FRA-2-", "", regex=False)
    if len(g) != 101:
        raise SystemExit(f"СТОП: в наборе границ {len(g)} единиц FRA-2-*, ожидалось 101")
    cols = ["unit_id", "code", "name"] + (["geometry"] if geometry else [])
    g = g.sort_values("unit_id")
    return g[cols].reset_index(drop=True) if geometry else pd.DataFrame(g[cols]).reset_index(drop=True)


def write_layer(layer: str, df: pd.DataFrame, value_cols: list[str], meta: dict,
                report: list[str]) -> Path:
    """CSV (SPEC_META §4.1 column order) + <layer>_<date>_meta.json + report md."""
    OUT.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().strftime("%Y%m%d")
    cols = ["unit_id", "name", "coverage_status", "coverage_note"] + value_cols
    csv = OUT / f"layer_{layer}_{date}.csv"
    df[cols].sort_values("unit_id").to_csv(csv, index=False, encoding="utf-8")
    meta = {"layer": layer, "snapshot_date": date, "rows": int(len(df)),
            "n_covered": int((df["coverage_status"] == "covered").sum()),
            "n_not_covered": int((df["coverage_status"] == "not_covered").sum()), **meta}
    (OUT / f"layer_{layer}_{date}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (RES / f"build_{layer}_{date}.md").write_text("\n".join(report), encoding="utf-8")
    print(f"CSV:    {csv}  ({len(df)} строк)")
    print(f"meta:   {OUT / f'layer_{layer}_{date}_meta.json'}")
    print(f"отчёт:  {RES / f'build_{layer}_{date}.md'}")
    return csv
