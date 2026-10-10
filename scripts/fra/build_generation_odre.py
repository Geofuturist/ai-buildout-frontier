r"""Layer energy_generation_odre_adm2 (SPEC_FRA_layers_v0_1 r4, §3).

Run from the repo root::

    python scripts\fra\build_generation_odre.py

Input: ODRÉ «Registre national des installations de production et de stockage
d'électricité» (aggregated), CSV, snapshot «au 31/07/2026».

Rules (proposals from PREFLIGHT_FRA §2, [ARCH] 10.10: build on them, [RES] approves):
  - operating = no dateDeraccordement, commissioning date not after the snapshot,
    regime != «En retrait provisoire»; rows without a commissioning date or without
    regime stay in;
  - storage = filiere «Stockage non hydraulique» -> storage_capacity_mw, not in
    installed_capacity_mw; pumped hydro stays in hydro as the source classifies it;
  - capacity = puisMaxInstallee (kW) / 1000;
  - join by codeDepartement (by code, not geometry); rows without a code and codes outside
    the 101 departments (975, 977, 978) are excluded and reported.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fra_common import ROOT, dept_code, input_entry, load_frame, rules_file, write_layer  # noqa: E402

LAYER = "generation_odre"
SRC_DIR = ROOT / "odre_registre"
SNAPSHOT = pd.Timestamp("2026-07-31")
EDITION = "au 31/07/2026"
SOURCE_URL = ("https://odre.opendatasoft.com/explore/dataset/"
              "registre-national-installation-production-stockage-electricite-agrege/")
STORAGE_FILIERE = "Stockage non hydraulique"
GROUPS = {  # filiere -> group (PREFLIGHT_FRA §2; [RES] approves)
    "Nucléaire": "nuclear", "Thermique non renouvelable": "fossil", "Hydraulique": "hydro",
    "Eolien": "wind", "Solaire": "solar", "Bioénergies": "bioenergy",
    "Energies Marines": "other", "Géothermie": "other", "Autre": "other",
}
# [RES] 10.10 §4: closed plants list (station, unit, source) and the decisions journal (codeEIC).
# A name hit among rows without a commissioning date stops the build unless the journal holds
# a decision for that codeEIC.
# Both live in data\fra\rules\ (in git, SPEC_FRA r5 §6 p.4); missing file -> stop.
CLOSED_LIST = rules_file("closed_plants.csv")
DECISIONS = rules_file("build_decisions_odre.csv")
GROUP_COLS = [f"capacity_{g}_mw" for g in
              ("nuclear", "fossil", "hydro", "wind", "solar", "bioenergy", "other")]


def main() -> None:
    files = sorted(SRC_DIR.glob("registre-national-installation-production-stockage-electricite-agrege*.csv"))
    if not files:
        sys.exit(f"СТОП: нет CSV реестра в {SRC_DIR}")
    src = files[0]
    df = pd.read_csv(src, sep=";", dtype=str, encoding="utf-8-sig", low_memory=False)
    need = ["codeDepartement", "filiere", "puisMaxInstallee", "dateDeraccordement",
            "dateMiseEnservice (format date)", "regime", "nbInstallations"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        sys.exit(f"СТОП: в реестре нет колонок {miss}")
    df["filiere"] = df["filiere"].map(lambda v: unicodedata.normalize("NFC", v.strip())
                                      if isinstance(v, str) else v)
    unknown = sorted(set(df["filiere"].dropna()) - set(GROUPS) - {STORAGE_FILIERE})
    if unknown:
        sys.exit(f"СТОП: новые значения filiere {unknown} — нужна таблица групп от [RES]")

    df["kw"] = pd.to_numeric(df["puisMaxInstallee"].str.replace(",", "."), errors="coerce")
    df["n"] = pd.to_numeric(df["nbInstallations"], errors="coerce")
    d_on = pd.to_datetime(df["dateMiseEnservice (format date)"], errors="coerce", format="%Y-%m-%d")
    d_off = pd.to_datetime(df["dateDeraccordement"], errors="coerce", dayfirst=True)
    off = d_off.notna()
    future = d_on > SNAPSHOT
    retired_tmp = df["regime"].eq("En retrait provisoire")
    df["operating"] = ~off & ~future & ~retired_tmp
    df["storage"] = df["filiere"].eq(STORAGE_FILIERE)
    df["group"] = df["filiere"].map(GROUPS)
    df["dep"] = df["codeDepartement"].map(dept_code)

    frame = load_frame()
    codes = set(frame["code"])
    op = df[df["operating"]]
    in_frame = op["dep"].isin(codes)
    gen = op[in_frame & ~op["storage"]]
    sto = op[in_frame & op["storage"]]

    agg = pd.DataFrame(index=sorted(codes))
    agg["installed_capacity_mw"] = gen.groupby("dep")["kw"].sum() / 1000
    agg["storage_capacity_mw"] = sto.groupby("dep")["kw"].sum() / 1000
    for g, col in zip(("nuclear", "fossil", "hydro", "wind", "solar", "bioenergy", "other"),
                      GROUP_COLS):
        agg[col] = gen[gen["group"] == g].groupby("dep")["kw"].sum() / 1000
    agg["n_installations"] = op[in_frame].groupby("dep")["n"].sum()
    agg = agg.fillna(0.0)
    agg["n_installations"] = agg["n_installations"].astype(int)
    agg["data_snapshot_date"] = SNAPSHOT.strftime("%Y-%m-%d")

    out = frame.merge(agg, left_on="code", right_index=True, how="left")
    # the register covers metropolitan France and the non-interconnected zones (ZNI):
    # every one of the 101 departments is covered; no row = 0 MW.
    out["coverage_status"] = "covered"
    out["coverage_note"] = ""

    # ---- totals_vs_source (SPEC_FRA §3): departments + excluded = source, to the kW
    gen_all = op[~op["storage"]]
    exc_nodep = gen_all[gen_all["dep"].isna()]
    exc_out = gen_all[gen_all["dep"].notna() & ~gen_all["dep"].isin(codes)]
    exc_nan = gen_all["kw"].isna().sum()
    lhs_kw = out["installed_capacity_mw"].sum() * 1000 + exc_nodep["kw"].sum() + exc_out["kw"].sum()
    rhs_kw = gen_all["kw"].sum()
    ok = abs(lhs_kw - rhs_kw) < 1.0
    groups_ok = abs(out[GROUP_COLS].sum(axis=1) - out["installed_capacity_mw"]).max() < 1e-6

    rep = [f"# Сборка `energy_generation_odre_adm2` · {pd.Timestamp.today():%Y-%m-%d}\n",
           f"Вход: `{src.name}` ({EDITION}).\n",
           "## Фильтр «действует»\n",
           "| условие | строк | МВт |", "|---|---|---|"]
    for lbl, m in (("отключены (`dateDeraccordement`)", off),
                   (f"ввод позже {SNAPSHOT:%d.%m.%Y}", future),
                   ("`regime` = En retrait provisoire", retired_tmp),
                   ("действуют (в расчёте)", df["operating"])):
        rep.append(f"| {lbl} | {int(m.sum()):,} | {df.loc[m, 'kw'].sum() / 1000:,.1f} |")
    # [RES] 10.10 §1.2: the ten largest rows without a commissioning date; closed plants -> stop
    nodate = df[df["operating"] & d_on.isna()].nlargest(10, "kw")
    name_col = "nomInstallation" if "nomInstallation" in df else None
    rep += ["\n## Десять крупнейших строк без даты ввода ([RES] 10.10, §1.2)\n",
            "| название | codeEIC | filiere | департамент | МВт |", "|---|---|---|---|---|"]
    rep += [f"| {r.get(name_col, '') if name_col else ''} | {r.get('codeEICResourceObject', '')} | "
            f"{r['filiere']} | {r['dep']} | {r['kw'] / 1000:,.1f} |" for _, r in nodate.iterrows()]
    cl = pd.read_csv(CLOSED_LIST, dtype=str).fillna("") if CLOSED_LIST.exists() else pd.DataFrame(
        columns=["station", "unit", "source_url"])
    dec = pd.read_csv(DECISIONS, dtype=str).fillna("") if DECISIONS.exists() else pd.DataFrame(
        columns=["codeEIC", "decision", "decided_by", "date"])
    decided = dict(zip(dec["codeEIC"], dec["decision"] + " (" + dec["decided_by"] + " " + dec["date"] + ")"))
    closed, logged = [], []
    for _, r in nodate.iterrows():
        nm = re.sub(r"[^A-Z0-9]", " ", unicodedata.normalize("NFKD", str(r.get(name_col, ""))).upper())
        for st in cl["station"]:
            if re.sub(r"[^A-Z]", " ", st.upper()) in nm:
                eic = str(r.get("codeEICResourceObject", ""))
                (logged if eic in decided else closed).append(
                    f"{r.get(name_col, '')} [{eic}]" + (f" — {decided[eic]}" if eic in decided else ""))
    rep.append(f"\nСписок закрытых станций: `{CLOSED_LIST.name}` ({len(cl)} строк). Совпадения по "
               f"названию без решения: {', '.join(closed) or 'нет'}.")
    rep.append(f"Совпадения с решением в журнале `{DECISIONS.name}`: {'; '.join(logged) or 'нет'}.\n")
    rep += ["\n## Итоги\n",
            f"- генерация в 101 департаменте: **{out['installed_capacity_mw'].sum():,.3f} МВт**;",
            f"- хранение (filiere «{STORAGE_FILIERE}»): {out['storage_capacity_mw'].sum():,.3f} МВт;",
            f"- число установок (`nbInstallations`, генерация и хранение): {int(out['n_installations'].sum()):,};",
            "\n## Исключено из департаментов (генерация, действующие)\n",
            f"- без кода департамента: {len(exc_nodep):,} строк, {exc_nodep['kw'].sum() / 1000:,.3f} МВт;",
            f"- код вне 101 департамента: {len(exc_out):,} строк, {exc_out['kw'].sum() / 1000:,.3f} МВт — "
            + ", ".join(f"{k}: {v / 1000:,.3f} МВт" for k, v in exc_out.groupby('dep')['kw'].sum().items()) + ";",
            f"- без числовой мощности: {int(exc_nan)} строк.",
            "\n## Проверки\n",
            f"- `totals_vs_source`: департаменты + исключённые = {lhs_kw:,.1f} кВт; источник "
            f"(действующие, без хранения) = {rhs_kw:,.1f} кВт — **{'OK' if ok else 'НЕ СХОДИТСЯ'}**;",
            f"- сумма групп = `installed_capacity_mw` в каждой строке: {'OK' if groups_ok else 'НЕТ'};",
            f"- строк: {len(out)} (нужно 101); покрыто: {int((out['coverage_status'] == 'covered').sum())}."]

    meta = {
        "source": "ODRÉ — Registre national des installations de production et de stockage "
                  "d'électricité (agrégé)",
        "publisher": "RTE, Enedis, EDF SEI, ELD",
        "source_url": SOURCE_URL,
        "edition": EDITION,
        "current_through": SNAPSHOT.strftime("%Y-%m-%d"),
        "license": "Licence Ouverte v2.0 (Etalab)",
        "inputs": [input_entry(src), input_entry(CLOSED_LIST), input_entry(DECISIONS)],
        "verification_method": (
            "operating = no dateDeraccordement AND commissioning date <= 2026-07-31 AND regime != "
            "'En retrait provisoire' (rows without commissioning date or regime kept); storage = "
            "filiere 'Stockage non hydraulique' (pumped hydro stays in hydro); capacity = "
            "puisMaxInstallee kW / 1000; joined by codeDepartement"),
        "rules_status": "approved by [RES] 10.10 (RES_to_CODE_FRA_preflight_answers_v1 §1)",
        "totals_vs_source": {"departments_plus_excluded_kw": lhs_kw, "source_kw": rhs_kw, "ok": ok},
        "excluded": {"no_department": {"rows": len(exc_nodep), "mw": exc_nodep["kw"].sum() / 1000},
                     "outside_frame": {"rows": len(exc_out), "mw": exc_out["kw"].sum() / 1000,
                                       "codes": sorted(exc_out["dep"].unique())}},
        "known_gaps_draft": [  # [RES] 10.10 §1.4, numbers from this build
            "Capacity is the maximum installed power (puissance maximale installée) declared in the "
            "register; it is not the net summer capacity of EIA-860, so the French and U.S. "
            "generation layers are not directly comparable.",
            f"Installations without a commissioning date in the register "
            f"({int((df['operating'] & d_on.isna()).sum())} rows, "
            f"{df.loc[df['operating'] & d_on.isna(), 'kw'].sum() / 1e6:,.1f} GW) are counted as "
            f"operating; installations temporarily withdrawn ({int(retired_tmp.sum())} rows, "
            f"{df.loc[retired_tmp, 'kw'].sum() / 1e6:,.1f} GW) are not.",
            "Small installations under 36 kW are aggregated in the source; they are included in "
            "the totals and in n_installations.",
            f"Installations without a department code ({exc_nodep['kw'].sum() / 1000:,.1f} MW) and "
            f"in Saint-Pierre-et-Miquelon, Saint-Barthélemy and Saint-Martin "
            f"({exc_out['kw'].sum() / 1000:,.1f} MW) are not in the department values.",
        ],
    }
    vals = ["installed_capacity_mw", "storage_capacity_mw", *GROUP_COLS, "n_installations",
            "data_snapshot_date"]
    write_layer(LAYER, out, vals, meta, rep)
    print("\n".join(rep[-4:]))
    if not ok:
        sys.exit("СТОП: totals_vs_source не сходится")
    if closed:
        sys.exit(f"СТОП ([RES] §1.2): среди строк без даты ввода похожие на закрытые: {closed}")


if __name__ == "__main__":
    main()
