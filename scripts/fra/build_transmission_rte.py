r"""Layer energy_transmission_rte_adm2 (+ unpublished segments) — SPEC_FRA_layers_v0_1 r4, §5.

Run from the repo root::

    python scripts\fra\build_transmission_rte.py

Input: DDTM de l'Eure copy of RTE «Lignes aériennes / souterraines» on data.gouv.fr
(data at 30.06.2023, lov2) — two shapefile archives in
D:\GISData\Energy\France\ddtm27_rte_lignes\. ODRÉ 2026 publishes the lines without
coordinates (RTE: «pour des raisons de sécurité publique»), so its attributes are NOT joined.

Outputs:
  data\fra\layer_transmission_rte_<date>.csv (+ meta, report)   -> handed to [CODE-PUB]
  D:\GISData\Energy\France\derived\rte_lines_segments\          -> segments, NEVER published
     (not in git, not in the release yaml, not on R2, not in the dev channel - decision V 10.10)

Method (same as HIFLD): line length INSIDE each department, EPSG:2154; departments =
FRA ADM2 of abf-boundaries-v0.1.0. Covered = the 94 continental departments; Corsica (2A, 2B)
and the five overseas departments are not_covered (RTE network is continental).
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fra_common import PRIVATE, ROOT, input_entry, load_frame, write_layer  # noqa: E402

LAYER = "transmission_rte"
SRC_DIR = ROOT / "ddtm27_rte_lignes"
SEG_DIR = PRIVATE / "rte_lines_segments"
NOT_COVERED = {"2A", "2B", "971", "972", "973", "974", "976"}
NOT_COVERED_NOTE = ("RTE's transmission network covers continental France; Corsica and the "
                    "overseas departments are run by EDF SEI and are not in this source")
BANDS = ["lt100", "100_199", "200_299", "300_399", "400_599", "ge600", "dc", "unknown"]
ODRE_URL = "https://odre.opendatasoft.com/explore/dataset/lignes-aeriennes-rte-nv/"
DDTM_URLS = ["https://www.data.gouv.fr/datasets/lignes-aeriennes-rte",
             "https://www.data.gouv.fr/datasets/lignes-souterraines-rte-1"]
RTE_QUOTE = ("RTE a fait évoluer l'accès aux données GPS des infrastructures du réseau public "
             "de transport pour des raisons de sécurité publique.")


def voltage_kv(t) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kV", str(t), re.I)
    if not m or str(t).strip().startswith("<"):
        return None
    return float(m.group(1).replace(",", "."))


def band(text, kv) -> str:
    t = str(text).upper()
    if "CONTINU" in t:
        return "dc"
    if t.strip().startswith("<"):           # «<45kV»: below 45 kV, number not exact
        return "lt100"
    if kv is None or pd.isna(kv):
        return "unknown"                     # HORS TENSION, empty
    for lim, b in ((100, "lt100"), (200, "100_199"), (300, "200_299"), (400, "300_399"),
                   (600, "400_599")):
        if kv < lim:
            return b
    return "ge600"


def read_segments():
    import geopandas as gpd
    zips = sorted(SRC_DIR.glob("*.zip"))
    if not zips:
        sys.exit(f"СТОП: нет архивов в {SRC_DIR}")
    parts = []
    for z in zips:
        for n in [n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith(".shp")]:
            g = gpd.read_file(f"zip://{z}!{n}").to_crs(2154)
            g["_file"] = f"{z.name}:{n}"
            parts.append(g)
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=2154)
    need = ["type_ouvra", "code_ligne", "etat", "tension"]
    miss = [c for c in need if c not in g.columns]
    if miss:
        sys.exit(f"СТОП: в shapefile нет колонок {miss}")
    return g, zips


def main() -> None:
    import geopandas as gpd
    seg, zips = read_segments()
    seg = seg[seg.geometry.notna() & ~seg.geometry.is_empty].copy()
    seg["line_type"] = seg["type_ouvra"].str.lower().map({"aerien": "overhead",
                                                          "souterrain": "underground"})
    seg["record_id"] = seg["code_ligne"].astype(str)
    seg["voltage_text"] = seg["tension"]
    seg["voltage_kv"] = seg["tension"].map(voltage_kv)
    seg["voltage_band"] = [band(t, k) for t, k in zip(seg["tension"], seg["voltage_kv"])]
    seg["owner_status"] = seg.get("proprietai")
    seg["state"] = seg["etat"]
    seg["km"] = seg.length / 1000

    # in operation only; lines «ACCORD ADMINISTRATIF» are projects with a permit (ODRÉ
    # field description) and are reported, not counted
    oper = seg["etat"].eq("EN EXPLOITATION")
    proj = seg[~oper]

    frame = load_frame(geometry=True).to_crs(2154)
    inter = gpd.overlay(seg[oper][["voltage_band", "voltage_kv", "geometry"]],
                        frame[["code", "geometry"]], how="intersection", keep_geom_type=True)
    inter["km"] = inter.length / 1000
    piv = inter.pivot_table(index="code", columns="voltage_band", values="km",
                            aggfunc="sum", fill_value=0.0)
    for b in BANDS:
        if b not in piv:
            piv[b] = 0.0
    out = pd.DataFrame(frame.drop(columns="geometry"))
    out = out.merge(piv[BANDS].add_prefix("km_"), left_on="code", right_index=True, how="left")
    km_cols = [f"km_{b}" for b in BANDS]
    out[km_cols] = out[km_cols].fillna(0.0)
    out["km_total"] = out[km_cols].sum(axis=1)
    out["max_voltage_kv"] = out["code"].map(inter.groupby("code")["voltage_kv"].max())
    out["has_any_line"] = out["km_total"] > 0
    out["frac_km_unknown_voltage"] = (out["km_unknown"] / out["km_total"]).where(out["km_total"] > 0)

    nc = out["code"].isin(NOT_COVERED)
    out["coverage_status"] = ["not_covered" if x else "covered" for x in nc]
    out["coverage_note"] = [NOT_COVERED_NOTE if x else "" for x in nc]
    vals = ["km_total", *km_cols, "max_voltage_kv", "has_any_line", "frac_km_unknown_voltage"]
    lines_in_nc = float(out.loc[nc, "km_total"].sum())
    out[vals] = out[vals].astype(object)
    out.loc[nc, vals] = None

    # ---- totals_vs_source: sum of departments = length of operating segments inside the 94
    covered_geom = frame[~frame["code"].isin(NOT_COVERED)].union_all()
    km_inside = seg[oper].intersection(covered_geom).length.sum() / 1000
    km_layer = out["km_total"].sum()
    km_all = seg.loc[oper, "km"].sum()
    diff = abs(km_layer - km_inside) / km_inside * 100
    ok = diff <= 0.5

    # ---- unpublished segments (decision V 10.10): local only, D:\ outside the repo
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    seg_out = seg[["record_id", "line_type", "voltage_text", "voltage_kv", "voltage_band",
                   "owner_status", "state", "geometry"]]
    seg_path = SEG_DIR / f"rte_lines_segments_ddtm2023_{pd.Timestamp.today():%Y%m%d}.gpkg"
    seg_out.to_file(seg_path, driver="GPKG", layer="segments")
    (SEG_DIR / "NOT_FOR_PUBLICATION.txt").write_text(
        "Сегменты ЛЭП RTE (копия DDTM, 30.06.2023). НЕ ПУБЛИКОВАТЬ: не в git, не в релиз, не на "
        "R2, не в канал dev. Решение V 10.10, SPEC_FRA r4 §5, ADR P9 «отозванная геометрия».\n",
        encoding="utf-8")

    bands_tbl = seg[oper].groupby("voltage_band")["km"].agg(["size", "sum"])
    rep = [f"# Сборка `energy_transmission_rte_adm2` · {pd.Timestamp.today():%Y-%m-%d}\n",
           "Вход: копия DDTM de l'Eure (данные на 30.06.2023): "
           + ", ".join(f"`{z.name}`" for z in zips) + ".\n",
           f"Сегментов: {len(seg):,}; в эксплуатации {int(oper.sum()):,} "
           f"({km_all:,.1f} км); «ACCORD ADMINISTRATIF» (проекты) — {len(proj):,} "
           f"({proj['km'].sum():,.1f} км), в расчёт не входят.\n",
           "## Полосы напряжения (в эксплуатации)\n", "| полоса | сегментов | км |", "|---|---|---|"]
    rep += [f"| {b} | {int(r['size']):,} | {r['sum']:,.1f} |" for b, r in bands_tbl.iterrows()]
    rep += ["\n## Проверки\n",
            f"- покрыто департаментов: {int((~nc).sum())}; с линиями: "
            f"{int(out.loc[~nc, 'has_any_line'].sum())}; км в не покрытых (должно быть 0): {lines_in_nc:,.1f};",
            f"- `totals_vs_source`: сумма `km_total` {km_layer:,.1f} км; сегменты внутри 94 департаментов "
            f"{km_inside:,.1f} км; расхождение {diff:.3f}% (допуск 0,5%) — **{'OK' if ok else 'НЕ СХОДИТСЯ'}**;",
            f"- вне 94 департаментов (берег, межгосударственные связи): {km_all - km_inside:,.1f} км;",
            f"- строк: {len(out)} (нужно 101).",
            f"\nСегменты (не публикуются) — `{seg_path}`."]
    meta = {
        "source": "RTE — Lignes aériennes RTE / Lignes souterraines RTE, copy published by DDTM de "
                  "l'Eure on data.gouv.fr (data at 30.06.2023)",
        "source_url": DDTM_URLS,
        "edition": "data at 2023-06-30 (DDTM 27 copy)",
        "current_through": "2023-06-30",
        "license": "Licence Ouverte v2.0 (lov2)",
        "inputs": [input_entry(z) for z in zips],
        "verification_method": (
            "segments with etat = 'EN EXPLOITATION' clipped to FRA ADM2 (abf-boundaries-v0.1.0) in "
            "EPSG:2154; length inside each department; voltage_kv parsed from 'tension'; "
            "'COURANT CONTINU' -> dc; 'HORS TENSION' -> unknown; '<45kV' -> lt100"),
        "segments_layer": "energy_transmission_lines_rte built locally, NOT published "
                          "(decision V 10.10, SPEC_FRA r4 §5)",
        "odre_attributes_joined": False,
        "totals_vs_source": {"km_layer": km_layer, "km_inside_94": km_inside, "diff_pct": diff, "ok": ok},
        "excluded": {"accord_administratif": {"segments": len(proj), "km": float(proj["km"].sum())},
                     "outside_departments_km": float(km_all - km_inside)},
        "known_gaps_draft": [
            "Line geometry is as of 30 June 2023, from the copy of RTE's dataset published by "
            "DDTM de l'Eure on data.gouv.fr.",
            f"In 2026 RTE stopped publishing line coordinates: «{RTE_QUOTE}» ({ODRE_URL}). The "
            "project therefore publishes only department totals, not the line segments.",
            "RTE does not publish substation coordinates; the project does not look for them.",
            f"Lines with an administrative approval that are not yet built (état ACCORD "
            f"ADMINISTRATIF) are not included: {proj['code_ligne'].nunique()} lines, "
            f"{proj['km'].sum():,.0f} km.",
            "Department boundaries are Natural Earth 1:10m; a line within about 1 km of a "
            "department boundary may be counted in the neighbouring department.",
        ],
    }
    write_layer(LAYER, out, vals, meta, rep)
    print("\n".join(rep[-6:]))
    if not ok:
        sys.exit("СТОП: totals_vs_source вне допуска")


if __name__ == "__main__":
    main()
