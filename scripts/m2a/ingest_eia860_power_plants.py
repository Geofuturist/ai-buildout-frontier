"""
ingest_eia860_power_plants.py
================================
EIA Form 860 (data year 2024, релиз 2025-09-09) -> infrastructure_raw.power_plants
SPEC_GCI_v2_0_M2a_pipeline.md §4.1

- Generator-файл, лист 'Operable', фильтр Status == 'OP' (SB исключается, см. raw_attributes).
- Поле: 'Summer Capacity (MW)' (литеральное имя колонки в файле — НЕ 'Net Summer Capacity').
- Join: Generator['Plant Code'] -> Plant['Plant Code'] -> Latitude/Longitude.
- Фильтр: State == 'VA' (физическое расположение станции по EIA, надёжно).
- source_id = "{PlantCode}-{GeneratorID}".
- region_id: точка(lon,lat) -> существующий триггер point->region (EPSG:4326).
  Без валидных координат -> region_id=NULL, geo_method='eia_county_fallback_unresolved',
  залогировать для ручной проверки (NE гадать матчингом по тексту округа — VA independent cities риск).

Запуск:
    python ingest_eia860_power_plants.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from gci_v2a_common import get_connection, upsert_rows, log

PLANT_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\2___Plant_Y2024.xlsx")
GENERATOR_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\3_1_Generator_Y2024.xlsx")

SOURCE = "EIA860_2024"
EIA_VINTAGE_NOTE = "EIA-860 data year 2024, final release 2025-09-09 (not 860M)"


def main() -> None:
    import pandas as pd

    if not PLANT_XLSX.exists() or not GENERATOR_XLSX.exists():
        log.error("Не найден один из файлов:\n  %s\n  %s", PLANT_XLSX, GENERATOR_XLSX)
        return

    log.info("Читаю Plant-файл...")
    plant_df = pd.read_excel(PLANT_XLSX, sheet_name="Plant", header=1)
    plant_lookup = {
        int(row["Plant Code"]): {
            "lat": row.get("Latitude"),
            "lon": row.get("Longitude"),
            "county": row.get("County"),
            "state": row.get("State"),
        }
        for _, row in plant_df.iterrows()
    }
    log.info("  %d станций в Plant-справочнике.", len(plant_lookup))

    log.info("Читаю Generator-файл, лист 'Operable'...")
    gen_df = pd.read_excel(GENERATOR_XLSX, sheet_name="Operable", header=1)
    log.info("  %d генераторов всего (все штаты, все статусы) в листе Operable.", len(gen_df))

    va_op = gen_df[(gen_df["State"] == "VA") & (gen_df["Status"] == "OP")].copy()
    va_sb_count = len(gen_df[(gen_df["State"] == "VA") & (gen_df["Status"] == "SB")])
    log.info(
        "  VA + Status=OP: %d генераторов. (Исключено VA Status=SB: %d — см. документацию решения ниже.)",
        len(va_op), va_sb_count,
    )

    rows = []
    unresolved_geo = []

    for _, row in va_op.iterrows():
        plant_code = int(row["Plant Code"])
        gen_id = str(row["Generator ID"]).strip()
        source_id = f"{plant_code}-{gen_id}"

        plant_info = plant_lookup.get(plant_code, {})
        lat, lon = plant_info.get("lat"), plant_info.get("lon")

        geo_method = None
        geom_wkt = None
        if lat is not None and lon is not None and not (lat == 0 and lon == 0):
            try:
                lat_f, lon_f = float(lat), float(lon)
                geom_wkt = f"SRID=4326;POINT({lon_f} {lat_f})"
                geo_method = "plant_coordinates"
            except (TypeError, ValueError):
                geom_wkt = None
        if geom_wkt is None:
            geo_method = "eia_county_fallback_unresolved"
            unresolved_geo.append(source_id)

        net_summer_mw = row.get("Summer Capacity (MW)")
        try:
            net_summer_mw = float(net_summer_mw) if net_summer_mw not in (None, "") else None
        except (TypeError, ValueError):
            net_summer_mw = None

        raw_attrs = {
            "vintage": EIA_VINTAGE_NOTE,
            "field_used": "Summer Capacity (MW)",
            "field_semantics": "EIA Net Summer Capacity (operable units, Schedule 3)",
            "status_filter": "Status == 'OP' only; excludes RE/proposed/SB (standby) — documented decision SPEC §4.1",
            "geo_method": geo_method,
            "plant_county_raw": plant_info.get("county"),
            "plant_state_raw": plant_info.get("state"),
            "technology": row.get("Technology"),
            "prime_mover_full": row.get("Prime Mover"),
            "energy_source_1": row.get("Energy Source 1"),
        }

        rows.append(
            (
                SOURCE,
                source_id,
                str(row.get("Plant Name", "")),
                net_summer_mw,
                str(row.get("Prime Mover", "")),
                str(row.get("Energy Source 1", "")),
                geom_wkt,
                None,  # region_id заполняется триггером point->region при geom is not null
                json.dumps(raw_attrs),
            )
        )

    if unresolved_geo:
        log.warning(
            "%d генераторов без валидных координат (region_id останется NULL, "
            "geo_method=eia_county_fallback_unresolved). Source_id для ручной проверки: %s",
            len(unresolved_geo), unresolved_geo,
        )

    conn = get_connection()
    try:
        upsert_rows(
            conn,
            table="infrastructure_raw.power_plants",
            columns=[
                "source", "source_id", "plant_name", "net_summer_capacity_mw",
                "prime_mover", "fuel_type", "geom", "region_id", "raw_attributes",
            ],
            rows=rows,
            conflict_cols=("source", "source_id"),
        )
    finally:
        conn.close()

    log.info("Готово: %d записей VA power_plants обработано.", len(rows))


if __name__ == "__main__":
    main()
