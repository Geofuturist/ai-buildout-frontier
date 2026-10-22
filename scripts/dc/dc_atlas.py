r"""abf-dc: Atlas of Data Center Politics copies -> records (SPEC_DC_world_v0_1_0 r2, section 2.1). Not run on its own.

Parsing is by column name (header of [SELECTION] and [RECORDS]), never by position. A repeated block of one
country is dropped as a block (the one with the later `exported_at` is kept, r2 Q9); rows inside a block are never merged.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

import pandas as pd

from dc_lib import BuildStop, norm, sha12, ws

MARK = {"SELECTION", "METRICS", "RECORDS", "RELATIONSHIPS"}
NEW_SELECTION_COLS = {"focus_type", "focus_name", "atlas_data_updated", "coverage_note"}
EXPECTED_BLOCKS, EXPECTED_COUNTRIES, EXPECTED_RECORDS = 129, 126, 9865


def parse_copy(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").split("\n")
    blocks, cur, sec = [], None, None
    for i, line in enumerate(lines, start=1):
        line = line.rstrip("\r")
        m = re.fullmatch(r"\[([A-Z]+)\]", line.strip())
        if m and m.group(1) in MARK:
            sec = m.group(1)
            if sec == "SELECTION":
                cur = dict(sel_h=None, sel=None, met={}, rec_h=None, rec=[])
                blocks.append(cur)
            continue
        if cur is None or sec is None or not line.strip():
            continue
        c = line.split("\t")
        if sec == "SELECTION":
            if cur["sel_h"] is None:
                cur["sel_h"] = c
            elif cur["sel"] is None:
                cur["sel"] = dict(zip(cur["sel_h"], c + [""] * (len(cur["sel_h"]) - len(c))))
        elif sec == "METRICS":
            if len(c) >= 3 and c[0] != "metric_group":
                cur["met"][c[1]] = c[2]
        elif sec == "RECORDS":
            if cur["rec_h"] is None:
                cur["rec_h"] = c
            else:
                cur["rec"].append((i, c))
    return blocks


def read_atlas(copies_dir: Path, report: list[str]):
    """-> (records DataFrame, blocks DataFrame, dropped-duplicate-blocks list)."""
    blocks = []
    for p in sorted(Path(copies_dir).iterdir()):
        if not p.is_file():
            continue
        for bi, b in enumerate(parse_copy(p), start=1):
            if b["sel"] is None or b["rec_h"] is None:
                raise BuildStop(f"{p.name} block {bi}: no [SELECTION] values or no [RECORDS] header")
            missing = NEW_SELECTION_COLS - set(b["sel_h"])
            if missing:
                raise BuildStop(f"{p.name} block {bi}: [SELECTION] has no columns {sorted(missing)}")
            b.update(file=p.name, bi=bi)
            blocks.append(b)
    if len(blocks) != EXPECTED_BLOCKS:
        raise BuildStop(f"{len(blocks)} blocks, expected {EXPECTED_BLOCKS}")
    rec_headers = {tuple(b["rec_h"]) for b in blocks}
    if len(rec_headers) != 1:
        raise BuildStop(f"[RECORDS] header differs between blocks ({len(rec_headers)} variants)")
    rec_h = list(next(iter(rec_headers)))

    brows = []
    for b in blocks:
        rows = []
        for ln, c in b["rec"]:
            if len(c) != len(rec_h):
                raise BuildStop(f"{b['file']} line {ln}: {len(c)} cells, header has {len(rec_h)}")
            rows.append((ln, dict(zip(rec_h, c))))
        b["rows"] = rows
        bad = [r["record_type"] for _, r in rows if r["record_type"] != "data_center"]
        if bad:
            raise BuildStop(f"{b['file']} block {b['bi']}: record_type other than data_center: {sorted(set(bad))}")
        if str(b["met"].get("all_sites", "")) != str(len(rows)):
            raise BuildStop(f"{b['file']} block {b['bi']} {b['sel']['selection_name']}: all_sites={b['met'].get('all_sites')} but {len(rows)} rows")
        s = b["sel"]
        brows.append(dict(file=b["file"], block=b["bi"], selection_name=s["selection_name"], scope_kind=s["scope_kind"], year_start=s["year_start"],
                          year_end=s["year_end"], active_filters=s["active_filters"], atlas_data_updated=s["atlas_data_updated"],
                          exported_at=s["exported_at"], all_sites=b["met"].get("all_sites", ""), n_rows=len(rows)))
    blocks_df = pd.DataFrame(brows)

    by_name = collections.defaultdict(list)
    for b in blocks:
        by_name[b["sel"]["selection_name"]].append(b)
    kept, dropped = [], []
    for name, bl in sorted(by_name.items()):
        bl = sorted(bl, key=lambda b: b["sel"]["exported_at"])
        kept.append(bl[-1])
        for old in bl[:-1]:
            same = collections.Counter(tuple(r.values()) for _, r in old["rows"]) == collections.Counter(tuple(r.values()) for _, r in bl[-1]["rows"])
            dropped.append(dict(selection_name=name, dropped=f"{old['file']}#{old['bi']}", kept=f"{bl[-1]['file']}#{bl[-1]['bi']}", identical_content=same,
                                n_rows=len(old["rows"])))
    if len(kept) != EXPECTED_COUNTRIES:
        raise BuildStop(f"{len(kept)} distinct block names after dropping repeats, expected {EXPECTED_COUNTRIES}")

    out = []
    for b in sorted(kept, key=lambda b: (b["file"], b["bi"])):
        s = b["sel"]
        for ln, r in b["rows"]:
            out.append(dict(r, _file=b["file"], _line=ln, _selection_name=s["selection_name"], _scope_kind=s["scope_kind"],
                            _active_filters=s["active_filters"], _exported_at=s["exported_at"], _atlas_data_updated=s["atlas_data_updated"]))
    df = pd.DataFrame(out)
    if len(df) != EXPECTED_RECORDS:
        raise BuildStop(f"{len(df)} Atlas records after dropping repeated blocks, expected {EXPECTED_RECORDS}")
    for d in dropped:
        report.append(f"- dropped repeated block {d['dropped']} ({d['selection_name']}, {d['n_rows']} rows); kept {d['kept']}; content identical: {d['identical_content']}")
    return df, rec_h, blocks_df, dropped


def add_ids_and_groups(df: pd.DataFrame, rec_h: list[str]) -> pd.DataFrame:
    """record_id = ATL- + first 12 hex of SHA-256 of all [RECORDS] fields in header order (NFC, whitespace collapsed, \\x1f);
    identical rows get -1, -2... by row order of the copy. A collision of different strings stops the build."""
    keys = df[rec_h].apply(lambda r: "\x1f".join(ws(v) for v in r), axis=1)
    base = keys.map(sha12)
    seen: dict[str, str] = {}
    for k, h in zip(keys, base):
        if seen.setdefault(h, k) != k:
            raise BuildStop(f"record_id collision (12 hex) for hash {h}")
    df = df.copy()
    df["_key"] = keys
    df["_base"] = base
    order = df.sort_values(["_file", "_line"]).groupby("_key").cumcount() + 1
    size = df.groupby("_key")["_key"].transform("size")
    df["record_id"] = [f"ATL-{b}" + (f"-{n}" if sz > 1 else "") for b, n, sz in zip(df["_base"], order.reindex(df.index), size)]
    df["identical_group"] = [f"IG-{b}" if sz > 1 else "" for b, sz in zip(df["_base"], size)]
    sk = df.apply(lambda r: "|".join([norm(r["country"]), norm(r["name_or_title"]), norm(r["address"]), norm(r["primary_actor"])]), axis=1)
    sksize = sk.groupby(sk).transform("size")
    df["same_key_group"] = [f"SK-{sha12(k)}" if n > 1 else "" for k, n in zip(sk, sksize)]
    if df["record_id"].duplicated().any():
        raise BuildStop("record_id is not unique")
    return df
