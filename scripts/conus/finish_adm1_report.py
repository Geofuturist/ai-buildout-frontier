r"""
finish_adm1_report.py
=====================
Run AFTER the four builders (SPEC_USA_states_v0_2_0 r5 section 2.6; SPEC_USA_AKHI_v0_3_0 r2). It does not
read any source; it only collects what the builders wrote into data\conus\:

    state_reconciliation_<date>.csv     the four reconciliation parts, one table
    sources_manifest_adm1_<date>.json   SHA-256 of every input and of every output
    build_report_adm1.md                numbers against expected, identities, everything that differs

The --states mode is taken from the parts (all four builders must have run with the same one).
With --states all the 49 contiguous rows of the reconciliation are compared with the 0.2.0 file
state_reconciliation_<prev-date>.csv: any difference is reported as not matching.

Run (from the repository root, cmd):
    python scripts\conus\finish_adm1_report.py --snapshot-date 20261109
"""

from __future__ import annotations

import adm1_common as C  # must be the first project import
from adm1_common import log
import datetime as dt
import json

import numpy as np
import pandas as pd

LAYERS = [
    ("generation_eia860", "EIA-860, generation (SPEC 2.2)"),
    ("queue_lbnl", "LBNL Queued Up, interconnection queue (SPEC 2.3)"),
    ("demand_nrel8562", "NREL OEDI 8562, peak demand (SPEC 2.4)"),
    ("transmission_hifld", "HIFLD, transmission lines (SPEC 2.5)"),
]
# states covered by each source, per --states mode (the others must be not_covered)
COVERED = {
    "contiguous": {l: C.CONTIGUOUS.fips for l, _ in LAYERS},
    "all": {"generation_eia860": C.make_scope("all").fips, "queue_lbnl": C.CONTIGUOUS.fips,
            "demand_nrel8562": C.CONTIGUOUS.fips, "transmission_hifld": C.make_scope("all").fips},
}
BASE_COLS = ["layer_id", "unit_id", "field", "unit", "state_value", "county_sum", "difference"]
TAIL_COLS = ["residual", "rounding_tolerance_km", "within_tolerance", "state_unrounded_km",
             "nrel_peak_hour_utc", "nrel_max_county_peak_mw", "nrel_ratio_state_to_sum", "nrel_n_county_columns", "detail"]


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return str(v)


def _mark(ok) -> str:
    return {True: "ok", False: "**НЕ СОШЛОСЬ**", None: "проверить"}[ok]


def compare_reconciliation(new: pd.DataFrame, prev_path) -> dict:
    """The rows of the 49 contiguous states of this reconciliation must equal the 0.2.0 file, row for row
    (key layer_id, unit_id, field): numbers to 1e-6, text and categories equal."""
    if not prev_path.exists():
        return {"status": "file not found", "file": prev_path.name}
    prev = pd.read_csv(prev_path, dtype={"unit_id": str}, keep_default_na=False, na_values=[""])
    key = ["layer_id", "unit_id", "field"]
    n = new.copy()
    n["unit_id"] = n["unit_id"].astype(str)
    n = n[n["unit_id"].str[-2:].isin(C.CONUS_STATES_FIPS)].set_index(key)
    p = prev[prev["unit_id"].str[-2:].isin(C.CONUS_STATES_FIPS)].set_index(key)
    problems = []
    if set(n.index) != set(p.index):
        problems.append(f"row keys differ: only new {len(set(n.index) - set(p.index))}, only 0.2.0 {len(set(p.index) - set(n.index))}")
    common = n.index.intersection(p.index)
    cols_new_only = [c for c in n.columns if c not in p.columns]
    cols_prev_only = [c for c in p.columns if c not in n.columns]
    if cols_new_only or cols_prev_only:
        problems.append(f"columns differ: only new {cols_new_only}, only 0.2.0 {cols_prev_only}")
    n_bad_cells = 0
    for c in [c for c in p.columns if c in n.columns]:
        a, b = n.loc[common, c], p.loc[common, c]
        an, bn = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
        numeric = an.notna().any() or bn.notna().any()
        if numeric and (an.notna() | a.isna()).all() and (bn.notna() | b.isna()).all():
            bad = (an.isna() != bn.isna()) | (an.notna() & bn.notna() & ((an - bn).abs() > C.FLOAT_TOL))
        else:
            bad = a.fillna("").astype(str) != b.fillna("").astype(str)
        if bad.any():
            n_bad_cells += int(bad.sum())
            problems.append(f"{c}: {int(bad.sum())} rows differ, first {list(common[bad.values][:2])}")
    return {"status": "OK" if not problems else "НЕ СОШЛОСЬ", "file": prev_path.name, "rows_compared": int(len(common)),
            "rows_in_0_2_0": int(len(p)), "problems": problems}


def main() -> None:
    ap = C.base_parser("Collect the ADM1 parts into state_reconciliation, the manifest and build_report_adm1.md")
    args = ap.parse_args()
    snap = args.snapshot_date
    out_dir = C.OUTPUT_DIR

    parts, recons, manifest = {}, [], {"snapshot_date": snap, "layers": {}}
    for layer, _ in LAYERS:
        pj = out_dir / f"adm1_part_{layer}_{snap}.json"
        pc = out_dir / f"adm1_recon_part_{layer}_{snap}.csv"
        if not pj.exists() or not pc.exists():
            raise SystemExit(f"STOP: no part for {layer} and date {snap}: run the builder first ({pj.name})")
        parts[layer] = json.loads(pj.read_text(encoding="utf-8"))
        recons.append(pd.read_csv(pc, dtype={"unit_id": str}))
    modes = {parts[l]["states"] for l, _ in LAYERS}
    if len(modes) != 1:
        raise SystemExit(f"STOP: the four builders ran with different --states: { {l: parts[l]['states'] for l, _ in LAYERS} }")
    mode = modes.pop()
    n_units = 51 if mode == "all" else 49
    version = "0.3.0" if mode == "all" else "0.2.0"

    # ---- state_reconciliation ---------------------------------------------------------------
    allr = pd.concat(recons, ignore_index=True)
    cat_cols = [c for c in allr.columns if c not in BASE_COLS + TAIL_COLS]
    cols = BASE_COLS + cat_cols + [c for c in TAIL_COLS if c in allr.columns]
    allr = allr[cols]
    rec_path = out_dir / f"state_reconciliation_{snap}.csv"
    allr.to_csv(rec_path, index=False)
    log.info("state_reconciliation: %s (%d rows)", rec_path, len(allr))
    recon_identity = compare_reconciliation(allr, out_dir / f"state_reconciliation_{args.prev_date}.csv")

    # ---- structural check of the four layer CSVs -------------------------------------------------
    struct = []
    akhi_rows = {}
    for layer, _ in LAYERS:
        p = out_dir / f"layer_{layer}_adm1_{snap}.csv"
        df = pd.read_csv(p, dtype={"unit_id": str})
        cov = COVERED[mode][layer]
        expect_cov = {f"USA-1-{f}" for f in cov}
        got_cov = set(df.loc[df["coverage_status"] == "covered", "unit_id"])
        ok = len(df) == 51 and got_cov == expect_cov
        struct.append((layer, p.name, len(df), len(got_cov), ok))
        akhi_rows[layer] = df[df["unit_id"].isin(["USA-1-02", "USA-1-15"])]
        entry = {"inputs": parts[layer]["inputs"], "output_csv": {"file": p.name, "sha256": C.sha256_file(p)}}
        ct = parts[layer].get("county_table")
        if ct:
            cp = out_dir / ct["file"]
            entry["county_table"] = {"file": cp.name, "rows": ct["rows"], "sha256": C.sha256_file(cp)}
        if parts[layer].get("segments"):
            entry["segments"] = {k: parts[layer]["segments"][k] for k in ("file", "sha256", "old_rows", "added_rows")}
        manifest["layers"][layer] = entry
    manifest["state_reconciliation"] = {"file": rec_path.name, "sha256": C.sha256_file(rec_path)}
    man_path = out_dir / f"sources_manifest_adm1_{snap}.json"
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    resid_bad = allr[(allr["residual"].abs() > 1e-6) & ~allr["layer_id"].str.contains("transmission_hifld")]
    hifld_bad = allr[allr["layer_id"].str.contains("transmission_hifld") & (allr["within_tolerance"] == False)]  # noqa: E712

    # ---- build_report_adm1.md ----------------------------------------------------------------------
    today = dt.date.today().strftime("%d.%m.%Y")
    L: list[str] = []
    L += [f"# build_report_adm1 · штаты США · `abf-layers` {version}", "",
          f"**Последняя правка:** {today} · r1 (собрано скриптом `finish_adm1_report.py`, дата данных {snap}, режим `--states {mode}`)",
          "**Основание:** SPEC_USA_states_v0_2_0 r5 §2" + ("; SPEC_USA_AKHI_v0_3_0 r2." if mode == "all" else "."), ""]

    all_checks = [(layer, c) for layer, _ in LAYERS for c in parts[layer]["checks"]]
    fails = [(l, c) for l, c in all_checks if c["ok"] is False]
    unk = [(l, c) for l, c in all_checks if c["ok"] is None]
    state_ident_ok = all(parts[l]["identity_state_prev"]["status"] == "OK" for l, _ in LAYERS)
    L += ["## 1. Итог", "",
          f"- Проверок: {len(all_checks)}; не сошлось: {len(fails)}; без автоматического вердикта: {len(unk)}.",
          "- Тождество округов с CSV 0.1.0 (3 109 смежных): " +
          ", ".join(f"{l}: {parts[l]['identity']['status']} ({parts[l]['identity']['n_counties_compared']} округов)"
                    for l, _ in LAYERS) + ".",
          "- Тождество 49 строк ADM1 с CSV сборки 0.2.0 (`" + args.prev_date + "`): " +
          ", ".join(f"{l}: {parts[l]['identity_state_prev']['status']} ({parts[l]['identity_state_prev']['n_states_compared']} штатов)"
                    for l, _ in LAYERS) + ".",
          f"- Тождество 49 штатов `state_reconciliation` с файлом `{recon_identity.get('file')}`: **{recon_identity['status']}**"
          + (f" ({recon_identity['rows_compared']} из {recon_identity['rows_in_0_2_0']} строк)" if "rows_compared" in recon_identity else "")
          + ".",
          f"- Остатки `state_reconciliation` (кроме HIFLD): строк с |остаток| > 1e-6: {len(resid_bad)}.",
          f"- HIFLD: строк вне допуска округления: {len(hifld_bad)}.",
          "- Структура четырёх CSV: " + ", ".join(f"{n}: {r} строк, {c} covered — {'ok' if ok else '**НЕ СОШЛОСЬ**'}"
                                                 for _, n, r, c, ok in struct) + ".", ""]
    if fails or recon_identity["status"] not in ("OK",):
        L += ["**Не сошлось:**", ""]
        L += [f"- `{l}`: {c['name']} — ожидалось {_fmt(c['expected'])}, получено {_fmt(c['actual'])}" for l, c in fails]
        L += [f"- `state_reconciliation`: {x}" for x in recon_identity.get("problems", [])]
        L += [""]

    if mode == "all":
        L += ["## 1а. Аляска и Гавайи по слоям", "", "| слой | единица | coverage_status | значения |", "|---|---|---|---|"]
        for layer, _ in LAYERS:
            for r in akhi_rows[layer].itertuples():
                vals = {k: v for k, v in r._asdict().items() if k not in ("Index", "unit_id", "coverage_status", "coverage_note")}
                shown = ", ".join(f"{k}={_fmt(v)}" for k, v in vals.items() if not (isinstance(v, float) and np.isnan(v)) and v is not pd.NA)
                L.append(f"| {layer} | {r.unit_id} | {r.coverage_status} | {shown or '—'} |")
        L.append("")

    for i, (layer, title) in enumerate(LAYERS, start=2):
        p = parts[layer]
        L += [f"## {i}. {title}", "", f"Слой `{p['layer_id']}`. Тождество округов с 0.1.0: **{p['identity']['status']}**, "
              f"сравнено {p['identity']['n_counties_compared']} округов, колонки: {', '.join(p['identity']['columns'])}.",
              f"Тождество 49 строк ADM1 с `{p['identity_state_prev']['file']}`: **{p['identity_state_prev']['status']}**, "
              f"колонки: {', '.join(p['identity_state_prev']['columns'])}.", "",
              "| Проверка | Ожидалось | Получено | Вердикт |", "|---|---|---|---|"]
        for c in p["checks"]:
            note = f" ({c['note']})" if c.get("note") else ""
            L.append(f"| {c['name']}{note} | {_fmt(c['expected'])} | {_fmt(c['actual'])} | {_mark(c['ok'])} |")
        L.append("")
        ct = p.get("county_table")
        if ct:
            tv = ct["text_vs_legacy"]
            L += [f"Таблица округов для выпуска: `{ct['file']}`, {ct['rows']} строк. Сверка текста с прежней таблицей "
                  f"`{tv.get('file')}`: **{tv.get('status')}**"
                  + (f" (сравнено {tv['rows_compared']} из {tv['rows_in_legacy']} строк, с отличием текста: "
                     f"{tv['rows_with_text_difference']}; колонки совпадают: {tv['columns_equal']})" if "rows_compared" in tv else "")
                  + ". Значения 3 109 округов уже доказаны тождественными CSV 0.1.0; эта строка — только про написание.", ""]
        lists = p.get("lists", {})
        if layer == "generation_eia860":
            L += ["Числа сборки:", "", "```", json.dumps(p["numbers"], indent=2, ensure_ascii=False), "```", "",
                  "Офшорные станции (в штатах есть, в округах нет):", ""]
            L += [f"- {r.get('plant_name')} ({r.get('key')}): {r.get('n_gens')} ген., {r.get('mw', 0):.1f} МВт"
                  for r in lists.get("offshore_plants", [])] or ["- нет"]
            L += ["", "Станции, у которых точка легла в округ другого штата:", ""]
            L += [f"- {r.get('plant_name')} (поле State {r.get('key')}, код округа {r.get('county_fips')}): "
                  f"{r.get('mw', 0):.1f} МВт" for r in lists.get("cross_state_plants", [])] or ["- нет (0)"]
        elif layer == "queue_lbnl":
            L += ["Числа сборки:", "", "```", json.dumps(p["numbers"], indent=2, ensure_ascii=False), "```", "",
                  "**Заявки, у которых штат поля `state` не совпадает со штатом кода округа** "
                  "(идут в штат из поля `state`, в округ — по коду; не исправлялись, для `known_gaps` [RES]7):", "",
                  "| q_id | поле state | код округа | МВт |", "|---|---|---|---|"]
            L += [f"| {r['q_id']} | {r['state']} | {r['county_fips']} | {r['mw']:.1f} |"
                  for r in lists.get("state_field_differs_from_county_code", [])] or ["| — | — | — | — |"]
            extra = lists.get("county_side_state_field_elsewhere_or_outside", [])
            L += ["", f"Записей в сумме округов, у которых поле `state` другое или вне 49 единиц: {len(extra)} "
                  "(в том числе перечисленные выше)."]
            L += ["", "Заявки с мощностью ≤ 0 (исключены):", "", "| q_id | регион | код округа | МВт |", "|---|---|---|---|"]
            L += [f"| {r['q_id']} | {r['region']} | {r['county_fips']} | {r['mw']:.1f} |" for r in lists.get("nonpositive", [])]
        elif layer == "demand_nrel8562":
            L += ["Числа сборки:", "", "```", json.dumps(p["numbers"], indent=2, ensure_ascii=False), "```", "",
                  f"Колонки файла, не вошедшие в слой: {lists.get('file_columns_not_in_layer') or 'нет'}.", "",
                  "Час пика — в UTC. По штатам:", "",
                  "| штат | колонок | пик штата, МВт | сумма пиков округов | наибольший пик округа | пик/сумма | час пика (UTC) |",
                  "|---|---|---|---|---|---|---|"]
            L += [f"| {r['state_fips']} | {r['n_county_columns']} | {r['peak_demand_mw']:,.1f} | {r['sum_county_peaks_mw']:,.1f} | "
                  f"{r['max_county_peak_mw']:,.1f} | {r['ratio_state_to_sum']:.4f} | {r['peak_hour_utc']} |"
                  for r in lists.get("per_state", [])]
        else:
            n = p["numbers"]
            L += ["Числа сборки:", "", "```", json.dumps(n, indent=2, ensure_ascii=False), "```", "",
                  f"Сегменты рамки 0.2.0, не лежащие ни в одном смежном округе: **{n['length_in_no_county_km']:,.1f} км** "
                  "(над водой за береговой линией cb 500k или за границей; их нет ни в округах, ни в штатах)."]
            sg = p.get("segments")
            if sg:
                L += ["", f"Файл сегментов `{sg['file']}`: {sg['new_rows']} линий = {sg['old_rows']} прежних + {sg['added_rows']} добавленных "
                      f"(по штатам: {sg['added_by_state_fips']}). Прежние сравнены с `{sg['old_file']}` по значениям: **{sg['status']}** "
                      f"({', '.join(sg['compared'])}). Повторяющихся ID в новом файле: {sg['duplicated_ids_in_new_file']}."]
        L.append("")

    L += ["## 6. Что осталось за другими", "",
          "- `coverage_note` в четырёх CSV пуст: тексты `not_covered` (свои у LBNL и NREL) вносит [CODE-PUB]2 в yaml, текст даёт [RES]7.",
          "- Колонка `name` в CSV не пишется (SPEC §2.1 п. 4): её ставит [CODE-PUB]2 из `units.csv`.",
          "- `known_gaps` в `_meta.json` — фактический черновик на английском; формулировки — [RES]7.",
          "- `home_bbox` и пути к новым таблицам округов и файлу сегментов в yaml — [CODE-PUB]2.",
          "- Коммит — после «да» V."]
    rep = out_dir / "build_report_adm1.md"
    rep.write_text("\n".join(L) + "\n", encoding="utf-8")
    log.info("Report: %s", rep)
    log.info("Manifest: %s", man_path)
    if fails or len(resid_bad) or len(hifld_bad) or not all(s[-1] for s in struct) or recon_identity["status"] != "OK" \
            or not state_ident_ok:
        log.warning("Something did not match: see the report section 1.")
        raise SystemExit(3)


if __name__ == "__main__":
    main()
