"""
ingest_berkeley_queue.py
===========================
Berkeley Lab "Queued Up" (LBNL_Ix_Queue_Data_File_thru2024_v2.xlsx, лист
"03. Complete Queue Data") -> infrastructure_raw.interconnection_queue
SPEC_GCI_v2_0_M2a_pipeline.md §4.3

- Гео-фильтр: ISO='PJM' (поле 'region' в источнике) И fips_codes начинается
  на '51' (Virginia). Прямой FIPS-джойн к core.regions — без spatial PIP,
  у источника нет lat/lon (подтверждено pre-flight).
- poi_request_mw = max(mw1, mw2, mw3), игнорируя 'NA' — правило для гибридов
  (не сумма компонентов, SPEC §4.3).
- Персистим ВСЕ статусы (active/withdrawn/suspended/operational) для аудита.
  Фильтр status='active' для реальной суммы contention — в compute-скрипте,
  НЕ здесь (SPEC §4.3: "прочие статусы персистим, но в contention не
  суммируем").
- source_id = q_id; если q_id == 'not assigned' (встречается в датафайле) —
  генерируем синтетический уникальный id, чтобы не столкнуться по UNIQUE.

Запуск:
    python ingest_berkeley_queue.py
"""

from __future__ import annotations

import json
from pathlib import Path

from gci_v2a_common import (
    get_connection,
    load_va_fips_region_map,
    upsert_rows,
    excel_serial_to_date,
    na_to_none,
    safe_float,
    log,
)

BERKELEY_XLSX = Path(r"D:\GISData\Energy\USA\LBNL_Ix_Queue_Data_File_thru2024_v2.xlsx")
SOURCE = "LBNL_QueuedUp_thru2024_v2"
SNAPSHOT_NOTE = "Berkeley Lab Queued Up, снапшот май-2026 (данные до конца 2025), emp.lbl.gov/queues"


def poi_request_mw(mw1, mw2, mw3) -> float | None:
    vals = [safe_float(v) for v in (mw1, mw2, mw3)]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def main() -> None:
    import pandas as pd

    if not BERKELEY_XLSX.exists():
        log.error("Файл не найден: %s", BERKELEY_XLSX)
        return

    conn = get_connection()
    try:
        fips_map = load_va_fips_region_map(conn)

        log.info("Читаю лист '03. Complete Queue Data' (может занять время, ~36k строк)...")
        df = pd.read_excel(BERKELEY_XLSX, sheet_name="03. Complete Queue Data", header=1)
        log.info("  Всего строк в датафайле: %d", len(df))

        df["fips_str"] = df["fips_codes"].apply(
            lambda v: str(int(v)).zfill(5) if pd.notna(v) and str(v).strip().upper() != "NA" else None
        )

        va_pjm = df[(df["region"] == "PJM") & (df["fips_str"].str.startswith("51", na=False))].copy()
        log.info("  После фильтра region=='PJM' & VA fips: %d строк.", len(va_pjm))

        if va_pjm.empty:
            log.warning("Ничего не найдено — проверь фильтр (литералы 'PJM'/fips формат).")
            return

        status_dist = va_pjm["q_status"].value_counts().to_dict()
        log.info("  Распределение q_status в VA+PJM: %s", status_dist)

        rows = []
        unassigned_counter = 0
        unresolved_region = []

        for idx, r in va_pjm.iterrows():
            raw_qid = na_to_none(r.get("q_id"))
            if raw_qid is None or str(raw_qid).strip().lower() == "not assigned":
                unassigned_counter += 1
                source_id = f"unassigned-{r['fips_str']}-{idx}-{unassigned_counter}"
            else:
                source_id = str(raw_qid)

            mw = poi_request_mw(r.get("mw1"), r.get("mw2"), r.get("mw3"))

            region_id = fips_map.get(r["fips_str"])
            if region_id is None:
                unresolved_region.append((source_id, r["fips_str"], r.get("county")))

            entered_date = excel_serial_to_date(r.get("q_date"))

            raw_attrs = {
                "snapshot": SNAPSHOT_NOTE,
                "q_status_raw": na_to_none(r.get("q_status")),
                "ia_status_clean": na_to_none(r.get("IA_status_clean")),
                "prop_date_raw": na_to_none(r.get("prop_date")),
                "on_date_raw": na_to_none(r.get("on_date")),
                "wd_date_raw": na_to_none(r.get("wd_date")),
                "mw1": safe_float(r.get("mw1")),
                "mw2": safe_float(r.get("mw2")),
                "mw3": safe_float(r.get("mw3")),
                "type1": na_to_none(r.get("type1")),
                "type2": na_to_none(r.get("type2")),
                "type3": na_to_none(r.get("type3")),
                "poi_request_mw_method": "max(mw1,mw2,mw3) excluding NA — hybrid POI rule, SPEC §4.3",
                "utility": na_to_none(r.get("utility")),
                "entity": na_to_none(r.get("entity")),
                "developer": na_to_none(r.get("developer")),
                "geo_method": "fips_direct_join",  # источник не даёт lat/lon — без spatial fallback risk
            }

            rows.append(
                (
                    SOURCE,
                    source_id,
                    str(na_to_none(r.get("project_name")) or ""),
                    str(na_to_none(r.get("region")) or ""),  # iso
                    str(na_to_none(r.get("q_status")) or ""),  # status (raw)
                    str(na_to_none(r.get("type_clean")) or na_to_none(r.get("type1")) or ""),  # fuel_type
                    mw,
                    str(na_to_none(r.get("county")) or ""),
                    str(na_to_none(r.get("state")) or ""),
                    entered_date,
                    None,  # geom — источник без lat/lon
                    region_id,
                    json.dumps(raw_attrs, default=str),
                )
            )

        if unresolved_region:
            log.warning(
                "%d записей с fips, не найденным в core.regions (region_id=NULL). "
                "Примеры (source_id, fips, county): %s",
                len(unresolved_region), unresolved_region[:10],
            )

        upsert_rows(
            conn,
            table="infrastructure_raw.interconnection_queue",
            columns=[
                "source", "source_id", "project_name", "iso", "status", "fuel_type",
                "poi_request_mw", "county_raw", "state_raw", "entered_date",
                "geom", "region_id", "raw_attributes",
            ],
            rows=rows,
            conflict_cols=("source", "source_id"),
        )
    finally:
        conn.close()

    log.info("Готово.")


if __name__ == "__main__":
    main()
