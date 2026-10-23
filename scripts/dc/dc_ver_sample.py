r"""abf-dc: sample frames for the independent check [CODE-DC]_ver (SPEC_DC_world_v0_1_0 r3, section 3 and section 10 item 2).

Run (Windows cmd, from the repo root)::

    python scripts\dc\dc_ver_sample.py --build-dir "D:\GISData\DC\out\abf-dc-v0.1.0" --out-dir "D:\GISData\DC\out\ver" --seed 20261023

Place sample (no network). Layers, each sampled separately; share 10% of the layer (rounded up), at least 5 (or all, if fewer):
  P1  one layer per source of the place and per layer of data: geonames_address, census_place, geonames_name, census_county
      (Atlas and Epoch separately)
  P2  region name: step 3 records where the matched words are the region name (PPLA / PPLC rule)
  P3  resolved_by_population = true
  P4  step 1 by alternatenames
Cell sample (checks.csv, network Full, from the links of the records): 10% (rounded up, at least 3 or all) of each stratum:
  C1  found by the script (strong key)   C2  found by V   C3  not_found by V   C4  not_found by the script
Cells of V are checked like the others and stay `human:V`.
The sample is deterministic: records are sorted by record_id, then `random.Random(seed).sample`.
Output: ver_sample_places.csv, ver_sample_cells.csv, ver_sample_summary.csv.
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

import pandas as pd

PLACE_MIN, CELL_MIN, SHARE = 5, 3, 0.10


def take(ids: list[str], rng: random.Random, minimum: int) -> list[str]:
    ids = sorted(ids)
    if not ids:
        return []
    n = min(len(ids), max(minimum, math.ceil(SHARE * len(ids))))
    return sorted(rng.sample(ids, n))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=20261023)
    a = ap.parse_args()
    B = a.build_dir
    rd = lambda n: pd.read_csv(B / n, dtype=str, keep_default_na=False)  # noqa: E731
    atl, epo, tr, chk = rd("dc_atlas_points.csv"), rd("dc_epoch_points.csv"), rd("place_trace.csv"), rd("checks.csv")
    tr = tr.set_index(["layer", "record_id"])
    rng = random.Random(a.seed)

    frames = []
    for layer, d in (("dc_atlas_points", atl), ("dc_epoch_points", epo)):
        t = tr.loc[layer]
        d = d.set_index("record_id").join(t[["step", "via", "basis_text", "region_match", "geonameid"]])
        has_place = d["coord_source"] != ""
        strata = [(f"P1:{layer}:{src}", d.index[d["coord_source"] == src].tolist()) for src in sorted(d.loc[has_place, "coord_source"].unique())]
        strata += [(f"P2:{layer}:region_name", d.index[(d["step"] == "3") & (d["region_match"] == "True")].tolist()),
                   (f"P3:{layer}:resolved_by_population", d.index[d["resolved_by_population"] == "true"].tolist()),
                   (f"P4:{layer}:step1_alternatenames", d.index[(d["step"] == "1") & (d["via"] == "alternatenames")].tolist())]
        for name, ids in strata:
            for rid in take(ids, rng, PLACE_MIN):
                r = d.loc[rid]
                frames.append(dict(sample_layer=name, layer=layer, record_id=rid, frame_size=len(ids), coord_source=r["coord_source"], coord_precision=r["coord_precision"],
                                   name=r["name"], operator_or_owner=r.get("operator", r.get("owner", "")), country=r["country_source"],
                                   adm1_raw=r.get("adm1_raw", ""), adm2_raw=r.get("adm2_raw", ""), address_raw=r["address_raw"], place_name=r["place_name"],
                                   place_ref=r["place_ref"], lon=r["lon"], lat=r["lat"], basis_text=r["basis_text"], via=r["via"], links=r.get("source_urls", r.get("selected_sources", ""))[:600]))
    places = pd.DataFrame(frames)

    strata = {
        "C1_found_script": chk[(chk.status == "found") & (chk.checked_by.str.startswith("script"))],
        "C2_found_V": chk[(chk.status == "found") & (chk.checked_by == "human:V")],
        "C3_not_found_V": chk[(chk.status == "not_found") & (chk.checked_by == "human:V")],
        "C4_not_found_script": chk[(chk.status == "not_found") & (chk.checked_by.str.startswith("script"))],
    }
    a_by = atl.set_index("record_id")
    e_by = epo.set_index("record_id")
    rows = []
    for name, d in strata.items():
        for rid in take(d["record_id"].tolist(), rng, CELL_MIN):
            r = d[d.record_id == rid].iloc[0]
            e = e_by.loc[rid]
            refs = [x for x in r["ref"].split(";") if x]
            rows.append(dict(sample_layer=name, record_id=rid, frame_size=len(d), status=r["status"], checked_by=r["checked_by"], checked_at=r["checked_at"], ref=r["ref"],
                             epoch_name=e["name"], epoch_owner=e["owner"], epoch_address=e["address_raw"], epoch_place=e["place_name"], epoch_links=e["selected_sources"][:800],
                             atlas_records="\n".join(f"{x} | {a_by.loc[x]['name']} | {a_by.loc[x]['operator']} | {a_by.loc[x]['address_raw'] or '(no address)'} | {a_by.loc[x]['source_urls'][:300]}" for x in refs if x in a_by.index)))
    cells = pd.DataFrame(rows)

    a.out_dir.mkdir(parents=True, exist_ok=True)
    places.to_csv(a.out_dir / "ver_sample_places.csv", index=False, lineterminator="\n")
    cells.to_csv(a.out_dir / "ver_sample_cells.csv", index=False, lineterminator="\n")
    summ = pd.concat([places.groupby("sample_layer").agg(frame=("frame_size", "first"), sampled=("record_id", "size")).reset_index(),
                      cells.groupby("sample_layer").agg(frame=("frame_size", "first"), sampled=("record_id", "size")).reset_index()])
    summ.to_csv(a.out_dir / "ver_sample_summary.csv", index=False, lineterminator="\n")
    print(summ.to_string(index=False))
    print("place rows", len(places), "unique records", places[["layer", "record_id"]].drop_duplicates().shape[0], "| cell rows", len(cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
