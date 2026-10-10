r"""Layer energy_consumption_agenceore_adm2 (SPEC_FRA_layers_v0_1 r4, §4; [RES] 10.10 §2).

Run from the repo root::

    python scripts\fra\build_consumption_agenceore.py

Input: Agence ORE «Consommation annuelle d'électricité et gaz par département»
(data-fair id 6l33py6xpnaolvzkckzkhcic), electricity only, last year in the file.

[RES] §2.2 — statistical secrecy is decided by an automated check first
(automated_checks id `secrecy_dept_vs_commune`): for the last year, electricity, each
department's total in the department file is compared with the sum of the commune file
(~840 MB, read in chunks). If the department total is never below the commune sum, secrecy
only acts at commune level and no `frac_masked` column is written; otherwise `frac_masked`
(share of the department's rows with secrecy) is added.

Sectors (CODE GRAND SECTEUR): RESIDENTIEL, TERTIAIRE, INDUSTRIE, AGRICULTURE, INCONNU; NAP and
empty -> unknown. n_delivery_points = sum of «Nb sites».
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fra_common import ROOT, dept_code, input_entry, load_frame, write_layer  # noqa: E402

LAYER = "consumption_agenceore"
SRC_DIR = ROOT / "agenceore_consommation"
DEPT_ID = "6l33py6xpnaolvzkckzkhcic"
COMMUNE_FILE = "consommation-annuelle-d-electricite-et-gaz-par-commune.csv"
SOURCE_URL = f"https://opendata.agenceore.fr/datasets/{DEPT_ID}"
SECTORS = {"RESIDENTIEL": "residential", "TERTIAIRE": "tertiary", "INDUSTRIE": "industry",
           "AGRICULTURE": "agriculture", "INCONNU": "unknown", "NAP": "unknown"}
SECTOR_COLS = [f"consumption_mwh_{s}" for s in
               ("residential", "tertiary", "industry", "agriculture", "unknown")]
TOL_MWH = 1.0  # rounding tolerance for the secrecy check


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def pick(cols, *cands) -> str | None:
    m = {norm(c): c for c in cols}
    for c in cands:
        if norm(c) in m:
            return m[norm(c)]
    for c in cands:
        for k, v in m.items():
            if norm(c) in k:
                return v
    return None


def sniff_sep(path: Path) -> str:
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        head = fh.readline()
    return max([";", ",", "\t"], key=head.count)


def commune_sums(path: Path, year: int) -> tuple[pd.Series, dict]:
    """Electricity, given year: sum of consumption per department from the commune file."""
    sep = sniff_sep(path)
    cols = pd.read_csv(path, sep=sep, nrows=0, encoding="utf-8-sig").columns
    c_year = pick(cols, "annee", "année")
    c_fil = pick(cols, "filiere")
    c_val = pick(cols, "conso_totale_mwh", "conso totale (mwh)", "consototale", "conso")
    c_dep = pick(cols, "code_departement", "code département", "codedepartement")
    c_com = pick(cols, "code_commune", "code commune", "codecommune", "code_insee")
    used = {"year": c_year, "energy": c_fil, "value": c_val, "dep": c_dep, "commune": c_com}
    if not (c_year and c_fil and c_val and (c_dep or c_com)):
        sys.exit(f"СТОП: в файле по коммунам не найдены нужные колонки: {used}; колонки: {list(cols)}")
    usecols = [c for c in (c_year, c_fil, c_val, c_dep, c_com) if c]
    total = pd.Series(dtype=float)
    for ch in pd.read_csv(path, sep=sep, usecols=usecols, dtype=str, chunksize=500_000,
                          encoding="utf-8-sig"):
        ch = ch[(pd.to_numeric(ch[c_year], errors="coerce") == year)
                & ch[c_fil].str.lower().str.contains("lec", na=False)]
        if ch.empty:
            continue
        dep = ch[c_dep].map(dept_code) if c_dep else ch[c_com].map(
            lambda v: (str(v).zfill(5)[:3] if str(v).zfill(5).startswith("97") else str(v).zfill(5)[:2])
            if pd.notna(v) else None)
        v = pd.to_numeric(ch[c_val].str.replace(",", "."), errors="coerce")
        total = total.add(v.groupby(dep).sum(), fill_value=0.0)
    return total, used


def main() -> None:
    src = SRC_DIR / f"{DEPT_ID}.csv"
    if not src.exists():
        sys.exit(f"СТОП: нет {src} — сначала download_fra.py")
    df = pd.read_csv(src, sep=sniff_sep(src), dtype=str, encoding="utf-8-sig")
    c = {k: pick(df.columns, *v) for k, v in {
        "year": ("Année",), "energy": ("FILIERE",), "dep": ("Code Département",),
        "sector": ("CODE GRAND SECTEUR",), "value": ("Conso totale (MWh)",),
        "sites": ("Nb sites",), "secret": ("Nombre de mailles secretisées",)}.items()}
    if None in c.values():
        sys.exit(f"СТОП: не найдены колонки {[k for k, v in c.items() if v is None]}")
    df["year"] = pd.to_numeric(df[c["year"]], errors="coerce")
    el = df[df[c["energy"]].str.lower().str.contains("lec", na=False)].copy()
    year = int(el["year"].max())
    el = el[el["year"] == year].copy()
    el["dep"] = el[c["dep"]].map(dept_code)
    el["v"] = pd.to_numeric(el[c["value"]].str.replace(",", "."), errors="coerce")
    el["sites"] = pd.to_numeric(el[c["sites"]].str.replace(",", "."), errors="coerce")
    el["secret"] = pd.to_numeric(el[c["secret"]].str.replace(",", "."), errors="coerce").fillna(0)
    el["sector"] = el[c["sector"]].map(SECTORS).fillna("unknown")

    frame = load_frame()
    codes = set(frame["code"])
    outside = sorted(set(el["dep"].dropna()) - codes)
    if outside:
        sys.exit(f"СТОП: коды вне рамки: {outside}")

    agg = pd.DataFrame(index=sorted(codes))
    agg["consumption_mwh"] = el.groupby("dep")["v"].sum()
    for s, col in zip(("residential", "tertiary", "industry", "agriculture", "unknown"), SECTOR_COLS):
        agg[col] = el[el["sector"] == s].groupby("dep")["v"].sum()
    agg[["consumption_mwh", *SECTOR_COLS]] = agg[["consumption_mwh", *SECTOR_COLS]].fillna(0.0)
    agg["n_delivery_points"] = el.groupby("dep")["sites"].sum().reindex(agg.index).fillna(0).astype(int)
    agg["data_year"] = year

    # ---- [RES] §2.2: secrecy_dept_vs_commune
    com_path = SRC_DIR / COMMUNE_FILE
    if not com_path.exists():
        sys.exit(f"СТОП: нет файла по коммунам {com_path} — нужен для проверки тайны ([RES] §2.2)")
    com, com_cols = commune_sums(com_path, year)
    chk = pd.DataFrame({"dept_file": agg["consumption_mwh"], "commune_sum": com}).fillna(0.0)
    chk["diff"] = chk["dept_file"] - chk["commune_sum"]
    below = chk[chk["diff"] < -TOL_MWH]
    secrecy_lowers = len(below) > 0
    # [RES] 10.10: frac_masked dropped; n_rows_without_value instead (rows the source
    # publishes without a value -> the department total is a lower bound)
    agg["n_rows_without_value"] = (el[el["v"].isna()].groupby("dep").size()
                                   .reindex(agg.index).fillna(0).astype(int))

    out = frame.merge(agg, left_on="code", right_index=True, how="left")
    out["coverage_status"] = "covered"
    out["coverage_note"] = ""
    empty_rows = el[el["v"].isna()]

    # ---- totals_vs_source: no national total in the file -> sum of the file
    file_sum = el["v"].sum()
    lay_sum = out["consumption_mwh"].sum()
    ok = abs(file_sum - lay_sum) < 1.0
    sectors_ok = abs(out[SECTOR_COLS].sum(axis=1) - out["consumption_mwh"]).max() < 1e-6

    rep = [f"# Сборка `energy_consumption_agenceore_adm2` · {pd.Timestamp.today():%Y-%m-%d}\n",
           f"Вход: `{src.name}`; электричество, {year}; {len(el):,} строк.\n",
           f"Итог: **{lay_sum:,.0f} МВт·ч**; по секторам: "
           + ", ".join(f"{col.split('_')[-1]} {out[col].sum():,.0f}" for col in SECTOR_COLS) + ".\n",
           "## Проверка `secrecy_dept_vs_commune` ([RES] §2.2)\n",
           f"Файл по коммунам `{com_path.name}`, колонки {com_cols}. Сумма по коммунам: "
           f"{com.sum():,.0f} МВт·ч; по файлу департаментов: {lay_sum:,.0f} МВт·ч.\n",
           f"Департаментов, где итог файла департаментов **меньше** суммы по коммунам "
           f"(допуск {TOL_MWH} МВт·ч): **{len(below)}**.\n"]
    if len(below):
        rep += ["| департамент | файл департаментов | сумма коммун | разница |", "|---|---|---|---|"]
        rep += [f"| {k} | {r['dept_file']:,.0f} | {r['commune_sum']:,.0f} | {r['diff']:,.0f} |"
                for k, r in below.sort_values("diff").iterrows()]
    nat_pct = (lay_sum - com.sum()) / com.sum() * 100
    max_below_pct = float((-below["diff"] / below["commune_sum"] * 100).max()) if len(below) else 0.0
    rep += [f"\nПо стране файл департаментов больше суммы коммун на {nat_pct:.2f}%; ниже — в "
            f"{len(below)} департаментах, не больше {max_below_pct:.3f}%. Решение [RES] 10.10: тайна "
            "действует на уровне коммун, итог департамента не занижает; `frac_masked` не публикуется.\n",
            f"Строк «департамент × сектор» с пустым значением: {len(empty_rows)} в "
            f"{empty_rows['dep'].nunique()} департаментах ({', '.join(sorted(empty_rows['dep'].dropna().unique()))}).\n",
            "## Проверки\n",
            f"- `totals_vs_source` (сумма файла, национального итога в нём нет): файл {file_sum:,.1f}, слой "
            f"{lay_sum:,.1f} МВт·ч — **{'OK' if ok else 'НЕ СХОДИТСЯ'}**;",
            f"- сумма секторов = итог в каждой строке: {'OK' if sectors_ok else 'НЕТ'};",
            f"- строк: {len(out)} (нужно 101); покрыто: {int((out['coverage_status'] == 'covered').sum())}."]
    vals = ["consumption_mwh", *SECTOR_COLS, "n_delivery_points", "n_rows_without_value", "data_year"]
    meta = {
        "source": "Agence ORE — Consommation annuelle d'électricité et gaz par département",
        "publisher": "Agence ORE",
        "source_url": SOURCE_URL,
        "edition": f"data year {year}, dataset updated 2026-01-06",
        "current_through": f"{year}-12-31",
        "license": "Licence Ouverte / Open Licence v1.0 (LicenseRef-etalab-1.0)",
        "inputs": [input_entry(src), input_entry(com_path)],
        "verification_method": (f"electricity rows, year {year}, summed by 'Code Département'; sectors "
                                "from 'CODE GRAND SECTEUR' (NAP -> unknown); n_delivery_points = sum of "
                                "'Nb sites'"),
        "automated_checks": [{"id": "secrecy_dept_vs_commune", "departments_below": len(below),
                              "dept_file_mwh": lay_sum, "commune_sum_mwh": float(com.sum()),
                              "result": f"department file exceeds the municipal sum by {nat_pct:.2f}% "
                                        f"nationally; lower in {len(below)} departments "
                                        f"({', '.join(below.index)}) by at most {max_below_pct:.2f}% — "
                                        "difference between extracts; department totals not reduced "
                                        "by secrecy ([RES] 10.10)"}],
        "fields_note": {"n_rows_without_value": (
            "Number of department × sector rows that the source publishes without a consumption "
            "value. When above 0, consumption_mwh and the sector columns of this department are "
            "lower bounds.")},
        "null_meaning": {"covered": None},
        "totals_vs_source": {"file_mwh": file_sum, "layer_mwh": lay_sum, "ok": ok},
        "known_gaps_draft": [  # [RES] 10.10
            "Annual metered energy in MWh, not peak power: not comparable with the modeled peak "
            "demand of the U.S. demand layer.",
            f"In {empty_rows['dep'].nunique()} departments the source publishes {len(empty_rows)} "
            "department × sector rows without a value; their consumption is not in the totals, so "
            "the totals of these departments are lower bounds (see n_rows_without_value).",
            f"Department totals are not reduced by the statistical confidentiality applied to "
            f"municipalities: the department file exceeds the sum of the municipal file by "
            f"{nat_pct:.2f}% nationally; in {len(below)} departments ({', '.join(below.index)}) it "
            f"is lower by at most {max_below_pct:.2f}%, which is treated as a difference between "
            "the two extracts.",
        ],
    }
    write_layer(LAYER, out, vals, meta, rep)
    print("\n".join(rep[-4:]))
    if not ok:
        sys.exit("СТОП: totals_vs_source не сходится")
    # [RES] 10.10 decision holds only while the extracts behave as on 10.10
    if nat_pct < 0 or max_below_pct > 0.1:
        sys.exit(f"СТОП: сверка тайны изменилась (по стране {nat_pct:.2f}%, max ниже "
                 f"{max_below_pct:.3f}%) — решение [RES] 10.10 нужно пересмотреть")


if __name__ == "__main__":
    main()
