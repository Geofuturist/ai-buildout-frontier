r"""
finish_adm1_report.py
=====================
Run AFTER the four builders (SPEC_USA_states_v0_2_0 r5, section 2.6). It does not read any source;
it only collects what the builders wrote into data\conus\:

    state_reconciliation_<date>.csv     the four reconciliation parts, one table
    sources_manifest_adm1_<date>.json   SHA-256 of every input and of every output
    build_report_adm1.md                numbers against expected, identity result, everything that differs

Run (from the repository root, cmd):
    python scripts\conus\finish_adm1_report.py --snapshot-date 20261101
"""

from __future__ import annotations

import adm1_common as C  # must be the first project import
from adm1_common import log
import datetime as dt
import json

import pandas as pd

LAYERS = [
    ("generation_eia860", "EIA-860, generation (SPEC 2.2)"),
    ("queue_lbnl", "LBNL Queued Up, interconnection queue (SPEC 2.3)"),
    ("demand_nrel8562", "NREL OEDI 8562, peak demand (SPEC 2.4)"),
    ("transmission_hifld", "HIFLD, transmission lines (SPEC 2.5)"),
]
BASE_COLS = ["layer_id", "unit_id", "field", "unit", "state_value", "county_sum", "difference"]
TAIL_COLS = ["residual", "rounding_tolerance_km", "within_tolerance", "state_unrounded_km",
             "nrel_peak_hour_utc", "nrel_max_county_peak_mw", "nrel_ratio_state_to_sum", "nrel_n_county_columns", "detail"]


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return str(v)


def _mark(ok) -> str:
    return {True: "ok", False: "**НЕ СОШЛОСЬ**", None: "проверить"}[ok]


def main() -> None:
    ap = C.base_parser("Collect the ADM1 parts into state_reconciliation, the manifest and build_report_adm1.md")
    snap = ap.parse_args().snapshot_date
    out_dir = C.OUTPUT_DIR

    parts, recons, manifest = {}, [], {"snapshot_date": snap, "layers": {}}
    for layer, _ in LAYERS:
        pj = out_dir / f"adm1_part_{layer}_{snap}.json"
        pc = out_dir / f"adm1_recon_part_{layer}_{snap}.csv"
        if not pj.exists() or not pc.exists():
            raise SystemExit(f"STOP: no part for {layer} and date {snap}: run the builder first ({pj.name})")
        parts[layer] = json.loads(pj.read_text(encoding="utf-8"))
        recons.append(pd.read_csv(pc, dtype={"unit_id": str}))

    # ---- state_reconciliation ---------------------------------------------------------------
    allr = pd.concat(recons, ignore_index=True)
    cat_cols = [c for c in allr.columns if c not in BASE_COLS + TAIL_COLS]
    cols = BASE_COLS + cat_cols + [c for c in TAIL_COLS if c in allr.columns]
    allr = allr[cols]
    rec_path = out_dir / f"state_reconciliation_{snap}.csv"
    allr.to_csv(rec_path, index=False)
    log.info("state_reconciliation: %s (%d rows)", rec_path, len(allr))

    # ---- structural check of the four layer CSVs -------------------------------------------------
    struct = []
    for layer, _ in LAYERS:
        p = out_dir / f"layer_{layer}_adm1_{snap}.csv"
        df = pd.read_csv(p, dtype={"unit_id": str})
        ok = (len(df) == 51 and int((df["coverage_status"] == "covered").sum()) == 49
              and set(df.loc[df["coverage_status"] == "not_covered", "unit_id"]) == {"USA-1-02", "USA-1-15"})
        struct.append((layer, p.name, len(df), int((df["coverage_status"] == "covered").sum()), ok))
        manifest["layers"][layer] = {"inputs": parts[layer]["inputs"],
                                     "output_csv": {"file": p.name, "sha256": C.sha256_file(p)}}
    manifest["state_reconciliation"] = {"file": rec_path.name, "sha256": C.sha256_file(rec_path)}
    man_path = out_dir / f"sources_manifest_adm1_{snap}.json"
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    resid_bad = allr[(allr["residual"].abs() > 1e-6) & ~allr["layer_id"].str.contains("transmission_hifld")]
    hifld_bad = allr[allr["layer_id"].str.contains("transmission_hifld") & (allr["within_tolerance"] == False)]  # noqa: E712

    # ---- build_report_adm1.md ----------------------------------------------------------------------
    today = dt.date.today().strftime("%d.%m.%Y")
    L: list[str] = []
    L += ["# build_report_adm1 · штаты США · `abf-layers` 0.2.0", "",
          f"**Последняя правка:** {today} · r1 (собрано скриптом `finish_adm1_report.py`, дата данных {snap})",
          "**Основание:** SPEC_USA_states_v0_2_0 r5, §2.", ""]

    all_checks = [(layer, c) for layer, _ in LAYERS for c in parts[layer]["checks"]]
    fails = [(l, c) for l, c in all_checks if c["ok"] is False]
    unk = [(l, c) for l, c in all_checks if c["ok"] is None]
    L += ["## 1. Итог", "",
          f"- Проверок: {len(all_checks)}; не сошлось: {len(fails)}; без автоматического вердикта: {len(unk)}.",
          f"- Тождество округов с CSV 0.1.0 (§2.1 п. 5): " +
          ", ".join(f"{l}: {parts[l]['identity']['status']} ({parts[l]['identity']['n_counties_compared']} округов)"
                    for l, _ in LAYERS) + ".",
          f"- Остатки `state_reconciliation` (кроме HIFLD): строк с |остаток| > 1e-6: {len(resid_bad)}.",
          f"- HIFLD: строк вне допуска округления: {len(hifld_bad)}.",
          "- Структура четырёх CSV: " + ", ".join(f"{n}: {r} строк, {c} covered — {'ok' if ok else '**НЕ СОШЛОСЬ**'}"
                                                 for _, n, r, c, ok in struct) + ".", ""]
    if fails:
        L += ["**Не сошлось:**", ""] + [f"- `{l}`: {c['name']} — ожидалось {_fmt(c['expected'])}, получено {_fmt(c['actual'])}" for l, c in fails] + [""]

    for i, (layer, title) in enumerate(LAYERS, start=2):
        p = parts[layer]
        L += [f"## {i}. {title}", "", f"Слой `{p['layer_id']}`. Тождество округов с 0.1.0: **{p['identity']['status']}**, "
              f"сравнено {p['identity']['n_counties_compared']} округов, колонки: {', '.join(p['identity']['columns'])}.", "",
              "| Проверка | Ожидалось | Получено | Вердикт |", "|---|---|---|---|"]
        for c in p["checks"]:
            note = f" ({c['note']})" if c.get("note") else ""
            L.append(f"| {c['name']}{note} | {_fmt(c['expected'])} | {_fmt(c['actual'])} | {_mark(c['ok'])} |")
        L.append("")
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
            L += ["Числа сборки:", "", "```", json.dumps(p["numbers"], indent=2, ensure_ascii=False), "```", "",
                  f"Сегменты в рамке CONUS, не лежащие ни в одном округе: **{p['numbers']['length_in_no_county_km']:,.1f} км** "
                  "(над водой за береговой линией cb 500k или за границей; их нет ни в округах, ни в штатах)."]
        L.append("")

    L += ["## 6. Что осталось за другими", "",
          "- `coverage_note` в четырёх CSV пуст: текст для Аляски и Гавайев даёт [RES]7, вносит [CODE-PUB]2.",
          "- Колонка `name` в CSV не пишется (SPEC §2.1 п. 4): её ставит [CODE-PUB]2 из `units.csv`.",
          "- `known_gaps` в `_meta.json` — фактический черновик на английском; формулировки — [RES]7.",
          "- Коммит — после «да» V."]
    rep = out_dir / "build_report_adm1.md"
    rep.write_text("\n".join(L) + "\n", encoding="utf-8")
    log.info("Report: %s", rep)
    log.info("Manifest: %s", man_path)
    if fails or len(resid_bad) or len(hifld_bad) or not all(s[-1] for s in struct):
        log.warning("Something did not match: see the report section 1.")


if __name__ == "__main__":
    main()
