"""
ingest_va_deq_dc_inventory.py
================================
va_deq_datacenters_with_mw.geojson -> infrastructure_raw.dc_inventory
SPEC_GCI_v2_0_M2a_pipeline.md §4.4

- status: литерал в источнике — 'operational' (100% записей, подтверждено
  pre-flight), что СОВПАДАЕТ с существующим enum infrastructure.dc_status
  напрямую (значение 'operational' уже в enum). Текст SPEC §4.4 говорит
  "status = operating" описательно, не литерально — фактического
  расхождения на уровне БД нет, фильтр работает как есть.
- capacity_mw уже в MW в источнике (конверсия HP/kW->MW сделана при
  скрапинге, mw_source документирует исходные единицы для аудита).
- cap_source = 'DEQ_backup_gen' (канонический короткий код для колонки;
  полная формулировка из источника — в raw_attributes.cap_note).
- geocoding_precision: источник использует coord_type, который НЕ совпадает
  литерально с existing enum (street_level/city/region/country_centroid).
  Скрипт показывает все встретившиеся значения coord_type и мапит их;
  немапленные значения -> NULL + warning (не гадаем).
- geom есть у всех 184 записей (даже jittered) -> региональный триггер
  point->region сработает как обычно.

Запуск:
    python ingest_va_deq_dc_inventory.py
"""

from __future__ import annotations

import json
from pathlib import Path

from gci_v2a_common import get_connection, upsert_rows, log

VA_DEQ_GEOJSON = Path(r"D:\GISData\Energy\USA\va_deq_datacenters_with_mw.geojson")

# Мапим coord_type источника -> existing enum infrastructure.geocoding_precision
# (street_level | city | region | country_centroid)
COORD_TYPE_MAP = {
    "county_centroid_jittered": "region",
    "exact_address": "street_level",
    "exact": "street_level",
    "geocoded_address": "street_level",
}


def main() -> None:
    if not VA_DEQ_GEOJSON.exists():
        log.error("Файл не найден: %s", VA_DEQ_GEOJSON)
        return

    with open(VA_DEQ_GEOJSON, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    feats = data.get("features", [])
    log.info("Прочитано %d features.", len(feats))

    coord_types_seen = {f["properties"].get("coord_type") for f in feats}
    log.info("Встретившиеся значения coord_type: %s", coord_types_seen)
    unmapped = coord_types_seen - set(COORD_TYPE_MAP.keys()) - {None}
    if unmapped:
        log.warning(
            "Немапленные coord_type значения (geocoding_precision будет NULL для них): %s",
            unmapped,
        )

    status_values = {f["properties"].get("status") for f in feats}
    log.info("Встретившиеся значения status: %s", status_values)
    unexpected_status = status_values - {
        "operational", "under_construction", "planned", "announced", "decommissioned", "unknown"
    }
    if unexpected_status:
        log.warning(
            "Значения status, не входящие в enum infrastructure.dc_status: %s "
            "(insert упадёт на этих записях — проверь вручную)",
            unexpected_status,
        )

    rows = []
    for f in feats:
        props = f["properties"]
        geom = f.get("geometry")

        reg_no = props.get("reg_no")
        if not reg_no:
            log.warning("Запись без reg_no — пропускаю: %s", props.get("name"))
            continue

        coord_type = props.get("coord_type")
        geocoding_precision = COORD_TYPE_MAP.get(coord_type)

        geom_wkt = None
        if geom and geom.get("type") == "Point":
            lon, lat = geom["coordinates"][0], geom["coordinates"][1]
            geom_wkt = f"SRID=4326;POINT({lon} {lat})"

        capacity_mw = props.get("capacity_mw")
        try:
            capacity_mw = float(capacity_mw) if capacity_mw is not None else None
        except (TypeError, ValueError):
            capacity_mw = None

        raw_attrs = {
            "county_raw": props.get("county"),
            "state_raw": props.get("state"),
            "mw_source": props.get("mw_source"),
            "cap_note": props.get("cap_note"),
            "n_permits": props.get("n_permits"),
            "permit_date": props.get("permit_date"),
            "permit_url": props.get("permit_url"),
            "coord_type_raw": coord_type,
            "conv_factor": 0.70,
            "conv_direction": "multiply",
            "conv_note": (
                "operating_DC_load_MW = 0.70 * capacity_mw применяется на этапе "
                "compute_gci_v2a_va.py, не здесь — capacity_mw в этой таблице "
                "это сырой backup-generator MW из air-permit (DEQ_backup_gen)."
            ),
        }

        rows.append(
            (
                str(props.get("source") or "VA_DEQ_air_permits_2024"),
                str(reg_no),
                str(props.get("name") or ""),
                str(props.get("operator") or ""),
                str(props.get("status") or "unknown"),
                capacity_mw,
                "DEQ_backup_gen",
                geocoding_precision,
                geom_wkt,
                None,  # region_id — заполняется триггером point->region
                json.dumps(raw_attrs, default=str),
            )
        )

    conn = get_connection()
    try:
        upsert_rows(
            conn,
            table="infrastructure_raw.dc_inventory",
            columns=[
                "source", "source_id", "name", "operator", "status", "capacity_mw",
                "cap_source", "geocoding_precision", "geom", "region_id", "raw_attributes",
            ],
            rows=rows,
            conflict_cols=("source", "source_id"),
        )
    finally:
        conn.close()

    log.info("Готово: %d записей dc_inventory обработано.", len(rows))


if __name__ == "__main__":
    main()
