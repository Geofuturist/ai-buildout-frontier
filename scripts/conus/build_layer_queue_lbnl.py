r"""
build_layer_queue_lbnl.py
============================
ТЗ-1, слой 5/5 (последний): queue_mw_active по округу, CONUS.
Berkeley Lab "Queued Up" -- LBNL_Ix_Queue_Data_File_thru2024_v2.xlsx.

Прямой FIPS-джойн (fips_codes -- собственное поле источника), НЕ
point-in-polygon -- источник не даёт lat/lon (подтверждено ещё в M2a).
Без фильтра по региону/ISO (в отличие от M2a, где был region=='PJM' для
Вирджинии) -- CONUS означает все ISO/BA сразу.

queue_mw_active = сумма poi_request_mw по округу СТРОГО для status=='active'.
Прочие статусы (withdrawn/suspended/operational) не публикуются в этом
слое -- ТЗ-1 просит именно активную очередь, не архив.

poi_request_mw = max(mw1,mw2,mw3), исключая 'NA' -- правило для гибридных
заявок (не сумма компонентов), то же самое, что в M2a.

Запуск (та же папка, что и gci_conus_common.py):
    python build_layer_queue_lbnl.py
    python build_layer_queue_lbnl.py --input-file D:\GISData\Energy\USA\<файл thru2025>.xlsx

--input-file (добавлено 09.10.2026, TZ_CODE_PILOT_eia860_2025_v1): файл издания
Queued Up; по умолчанию — прежний thru2024_v2. Логика слоя не менялась.

[ARCH] 09.10.2026, ADR 5.8 (both options are off by default, so a run without
them gives the old output byte for byte):
  --crosswalk <csv>   exact code changes (old unit wholly inside one new unit),
                      applied to the source county code before the join;
  --ct-not-covered    the 9 Connecticut planning regions (09110-09190) get
                      coverage_status = not_covered and an empty value: the
                      source codes Connecticut by pre-2022 counties.
[ARCH] 09.10.2026 (TZ part 2, r5):
  --drop-nonpositive  requests with max(mw1..3) <= 0 are left out of the sum and
                      the project count, and listed in known_gaps;
  --snapshot-date     output date tag (so a same-day rebuild never overwrites);
  the per-row reason column is coverage_note (empty for covered units).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from gci_conus_common import load_conus_counties, write_layer_outputs, na_to_none, safe_float, log

BERKELEY_XLSX = Path(r"D:\GISData\Energy\USA\LBNL_Ix_Queue_Data_File_thru2024_v2.xlsx")
LAYER_NAME = "queue_lbnl"
SOURCE_URL = "https://emp.lbl.gov/queues"
SNAPSHOT_NOTE = "снапшот май-2026 (данные до конца 2025)"
CROSSWALK = None      # set by --crosswalk
CT_NOT_COVERED = False  # set by --ct-not-covered
DROP_NONPOSITIVE = False  # set by --drop-nonpositive
SNAPSHOT = None  # set by --snapshot-date
CT_NULL_MEANING = ("The source codes Connecticut projects by pre-2022 counties, "
                   "which do not map onto the 2022 planning regions")


def poi_request_mw(mw1, mw2, mw3):
    vals = [v for v in (safe_float(mw1), safe_float(mw2), safe_float(mw3)) if v is not None]
    return max(vals) if vals else None


def _set_input_file() -> None:
    """--input-file: the only change (09.10.2026); default = thru2024_v2."""
    import argparse
    global BERKELEY_XLSX, CROSSWALK, CT_NOT_COVERED, DROP_NONPOSITIVE, SNAPSHOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file", default=str(BERKELEY_XLSX))
    ap.add_argument("--crosswalk", default=None)
    ap.add_argument("--ct-not-covered", action="store_true")
    ap.add_argument("--drop-nonpositive", action="store_true")
    ap.add_argument("--snapshot-date", default=None)
    args = ap.parse_args()
    BERKELEY_XLSX = Path(args.input_file)
    CROSSWALK = Path(args.crosswalk) if args.crosswalk else None
    CT_NOT_COVERED = args.ct_not_covered
    DROP_NONPOSITIVE = args.drop_nonpositive
    SNAPSHOT = args.snapshot_date
    log.info("Вход: %s", BERKELEY_XLSX)


def main() -> None:
    import pandas as pd

    _set_input_file()
    if not BERKELEY_XLSX.exists():
        log.error("Файл не найден: %s", BERKELEY_XLSX)
        return

    log.info("Читаю LBNL Queued Up...")
    df = pd.read_excel(BERKELEY_XLSX, sheet_name="03. Complete Queue Data", header=1)
    # [ARCH] 09.10.2026: Queued Up 2026 renamed the columns this script reads.
    # Map them back right after reading, only when the new names are present;
    # with the old file nothing is renamed and the output is byte-identical.
    renames = {"fips_code": "fips_codes", "mw_1": "mw1", "mw_2": "mw2", "mw_3": "mw3"}
    renames = {k: v for k, v in renames.items() if k in df.columns and v not in df.columns}
    if renames:
        df = df.rename(columns=renames)
        log.info("Издание с новыми именами колонок, сопоставлено: %s", renames)
    log.info("Всего строк: %d", len(df))

    active = df[df["q_status"] == "active"].copy()
    log.info("status=='active' (все ISO/BA, CONUS+не-CONUS вместе): %d", len(active))

    active["fips_str"] = active["fips_codes"].apply(
        lambda v: str(int(v)).zfill(5) if pd.notna(v) and str(v).strip().upper() != "NA" else None
    )
    n_no_fips = active["fips_str"].isna().sum()
    log.info("Без fips_codes (не попадут в агрегацию): %d/%d (%.1f%%)", n_no_fips, len(active), 100 * n_no_fips / len(active))

    active["poi_mw"] = active.apply(lambda r: poi_request_mw(r["mw1"], r["mw2"], r["mw3"]), axis=1)

    counties = load_conus_counties()
    valid_fips = set(counties["fips"])

    # [ARCH] 09.10.2026, ADR 5.8: exact code changes, before the join.
    recoded = []
    if CROSSWALK is not None:
        cw = pd.read_csv(CROSSWALK, dtype=str)
        for _, c in cw.iterrows():
            m = active["fips_str"] == c["old_fips"].zfill(5)
            recoded.append({"old_fips": c["old_fips"], "new_fips": c["new_fips"],
                            "records": int(m.sum()), "mw": float(active.loc[m, "poi_mw"].sum())})
            active.loc[m, "fips_str"] = c["new_fips"].zfill(5)
            log.info("Перекодировано %s -> %s: %d записей, %.1f МВт", c["old_fips"],
                     c["new_fips"], m.sum(), active.loc[m, "poi_mw"].sum())

    ct_old = active[active["fips_str"].fillna("").str.startswith("09")
                    & ~active["fips_str"].isin(valid_fips)]
    ct_new = active[active["fips_str"].fillna("").str.startswith("09")
                    & active["fips_str"].isin(valid_fips)]
    if CT_NOT_COVERED:
        log.info("Коннектикут: старые коды %d записей (%.1f МВт); новые коды регионов %d записей "
                 "(%.1f МВт)", len(ct_old), ct_old["poi_mw"].sum(), len(ct_new),
                 ct_new["poi_mw"].sum())
    active_conus = active[active["fips_str"].isin(valid_fips)].copy()
    log.info("С fips, входящим в CONUS (%d округов): %d строк", len(valid_fips), len(active_conus))
    dropped = []
    if DROP_NONPOSITIVE:  # [ARCH] 09.10 r5: max(mw1..3) <= 0 is not a generation request
        bad = active_conus["poi_mw"].notna() & (active_conus["poi_mw"] <= 0)
        dropped = [{"q_id": str(r.get("q_id")), "region": str(r.get("region")),
                    "fips": r["fips_str"], "mw": float(r["poi_mw"])}
                   for _, r in active_conus[bad].iterrows()]
        active_conus = active_conus[~bad].copy()
        log.info("Исключено заявок с max(mw) <= 0: %d %s", len(dropped), dropped)

    agg = active_conus.groupby("fips_str").agg(
        queue_mw_active=("poi_mw", "sum"),
        n_active_projects=("poi_mw", "count"),
    ).reset_index().rename(columns={"fips_str": "fips"})

    result = counties.merge(agg, on="fips", how="left")
    result["queue_mw_active"] = result["queue_mw_active"].fillna(0.0)
    result["n_active_projects"] = result["n_active_projects"].fillna(0).astype(int)

    if CT_NOT_COVERED:
        ct = result["fips"].str.startswith("09")
        result["queue_mw_active"] = result["queue_mw_active"].where(~ct)
        result["n_active_projects"] = result["n_active_projects"].astype("Int64").where(~ct)
        result["coverage_status"] = ct.map({True: "not_covered", False: "covered"})
        result["coverage_note"] = ct.map({True: CT_NULL_MEANING, False: ""})
        log.info("Коннектикут not_covered: %d единиц", int(ct.sum()))

    n_zero = int((result["n_active_projects"] == 0).sum())
    log.info("Округов без активных заявок в очереди: %d/%d", n_zero, len(result))

    snapshot_date = SNAPSHOT or dt.date.today().strftime("%Y%m%d")
    meta = {
        "source": "Berkeley Lab (LBNL) 'Queued Up' — interconnection queue database",
        "source_url": SOURCE_URL,
        "vintage": SNAPSHOT_NOTE,
        "license": "см. страницу emp.lbl.gov/queues (открытый доступ)",
        "coverage": "48 states + DC (CONUS), все ISO/BA (PJM, MISO, CAISO, ERCOT, и др.)",
        "n_units_covered": int(len(active_conus)),
        "n_units_no_data": int(n_no_fips),
        "known_gaps": (
            f"{n_no_fips}/{len(active)} записей status=='active' национально не имеют fips_codes "
            "в источнике — не попадают в county-агрегацию (прямой FIPS-джойн, без spatial fallback: "
            "источник не даёт lat/lon). Публикуются только status=='active' — withdrawn/suspended/"
            "operational заявки в этом слое не отражены, это активная очередь на сегодня, не архив. "
            "poi_request_mw = max(mw1,mw2,mw3) для гибридных заявок, не сумма компонентов."
        ),
    }

    out_cols = ["fips", "NAME", "NAMELSAD", "queue_mw_active", "n_active_projects"]
    if recoded:
        meta["code_crosswalk"] = {"file": str(CROSSWALK), "applied": recoded}
    if CT_NOT_COVERED:
        out_cols += ["coverage_status", "coverage_note"]
        meta["n_units_not_covered"] = int((result["coverage_status"] == "not_covered").sum())
        meta["known_gaps"] += (
            f" Connecticut: the source codes projects by pre-2022 counties; {len(ct_old)} active "
            f"records ({ct_old['poi_mw'].sum():.1f} MW) cannot be placed in the 2022 planning "
            "regions, so all 9 regions are not_covered (no value, not zero)."
        )
        if len(ct_new):
            meta["known_gaps"] += (f" {len(ct_new)} Connecticut records already carry region "
                                   "codes and are also left out with the regions.")
    if dropped:
        meta["excluded_nonpositive"] = dropped
        meta["known_gaps"] += (
            " Requests whose largest capacity field is zero or negative are left out of the sum "
            "and the project count: " + "; ".join(
                f"{d['q_id']} ({d['region']}, county {d['fips']}, {d['mw']:g} MW)" for d in dropped)
            + ".")
    write_layer_outputs(
        LAYER_NAME,
        result[out_cols + ["geometry"]],
        meta,
        snapshot_date,
    )
    log.info("ГОТОВО.")


if __name__ == "__main__":
    main()
