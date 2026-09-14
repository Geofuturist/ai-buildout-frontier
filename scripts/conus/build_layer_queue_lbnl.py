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
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from gci_conus_common import load_conus_counties, write_layer_outputs, na_to_none, safe_float, log

BERKELEY_XLSX = Path(r"D:\GISData\Energy\USA\LBNL_Ix_Queue_Data_File_thru2024_v2.xlsx")
LAYER_NAME = "queue_lbnl"
SOURCE_URL = "https://emp.lbl.gov/queues"
SNAPSHOT_NOTE = "снапшот май-2026 (данные до конца 2025)"


def poi_request_mw(mw1, mw2, mw3):
    vals = [v for v in (safe_float(mw1), safe_float(mw2), safe_float(mw3)) if v is not None]
    return max(vals) if vals else None


def main() -> None:
    import pandas as pd

    if not BERKELEY_XLSX.exists():
        log.error("Файл не найден: %s", BERKELEY_XLSX)
        return

    log.info("Читаю LBNL Queued Up...")
    df = pd.read_excel(BERKELEY_XLSX, sheet_name="03. Complete Queue Data", header=1)
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
    active_conus = active[active["fips_str"].isin(valid_fips)].copy()
    log.info("С fips, входящим в CONUS (%d округов): %d строк", len(valid_fips), len(active_conus))

    agg = active_conus.groupby("fips_str").agg(
        queue_mw_active=("poi_mw", "sum"),
        n_active_projects=("poi_mw", "count"),
    ).reset_index().rename(columns={"fips_str": "fips"})

    result = counties.merge(agg, on="fips", how="left")
    result["queue_mw_active"] = result["queue_mw_active"].fillna(0.0)
    result["n_active_projects"] = result["n_active_projects"].fillna(0).astype(int)

    n_zero = int((result["n_active_projects"] == 0).sum())
    log.info("Округов без активных заявок в очереди: %d/%d", n_zero, len(result))

    snapshot_date = dt.date.today().strftime("%Y%m%d")
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

    write_layer_outputs(
        LAYER_NAME,
        result[["fips", "NAME", "NAMELSAD", "queue_mw_active", "n_active_projects", "geometry"]],
        meta,
        snapshot_date,
    )
    log.info("ГОТОВО.")


if __name__ == "__main__":
    main()
