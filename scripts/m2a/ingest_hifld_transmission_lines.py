"""
ingest_hifld_transmission_lines.py
=====================================
HIFLD Transmission Lines (nationwide shapefile, EPSG:3857) ->
infrastructure_raw.transmission_lines
SPEC_GCI_v2_0_M2a_pipeline.md §4.2

- Источник: VA + соседние штаты — линии, которые МОГУТ пересекать границы
  VA-округов. Фильтруем по bbox VA + буфер (получаем bbox из core.regions,
  буферим, репроецируем в 3857 для partial-read шейпфайла).
- STATUS: по решению V — включаем И 'IN SERVICE', И 'NOT AVAILABLE'
  (NOT AVAILABLE = метаданные не заполнены, не "выведена из эксплуатации";
  явные неоперационные статусы типа UNDER CONSTRUCTION/RETIRED/DE-ENERGIZED
  исключались бы, но в реальных данных таких значений нет).
- DLR: пропускаем полностью (см. решение в чате — NREL/NLR файлы по 19GB
  нецелесообразны для подмножества граничных линий VA). dlr_thermal_mw
  остаётся NULL для всех строк; voltage_thermal_lookup применяется позже,
  в compute_gci_v2a_va.py, на основе voltage_kv (не дублируем логику здесь).
- VOLTAGE sentinel -999999.0 -> voltage_kv = NULL (попадёт в "<69/unknown"
  бакет lookup-таблицы на этапе compute).
- source_id = поле 'ID' (литеральное имя колонки в HIFLD-шейпфайле).
- region_ids[] заполняется существующим триггером line->region_ids
  (infrastructure.powerlines_set_regions) автоматически при INSERT.

Зависимости: geopandas, shapely, pyproj (обычно тянутся вместе).

Запуск:
    python ingest_hifld_transmission_lines.py
"""

from __future__ import annotations

import json
from pathlib import Path

from gci_v2a_common import get_connection, upsert_rows, log

HIFLD_SHP = Path(
    r"D:\GISData\Energy\USA\US_Electric_Power_Transmission_Lines_-8378795084787321001"
    r"\Electric_Power_Transmission_Lines_A.shp"
)

SOURCE = "HIFLD_transmission_lines"
BUFFER_DEGREES = 0.6  # ~65 км на широте VA — консервативный запас для граничных линий из соседних штатов
ALLOWED_STATUSES = {"IN SERVICE", "NOT AVAILABLE"}  # решение V; явные RETIRED/etc. исключались бы, если появятся


def get_va_bbox_buffered(conn):
    """Bbox VA (core.regions, EPSG:4326) + буфер в градусах."""
    with conn.cursor() as cur:
        cur.execute(
            "select st_xmin(ext), st_ymin(ext), st_xmax(ext), st_ymax(ext) "
            "from (select st_extent(geometry) as ext from core.regions "
            "      where admin_code like '51%%') t"
        )
        xmin, ymin, xmax, ymax = cur.fetchone()
    return (xmin - BUFFER_DEGREES, ymin - BUFFER_DEGREES, xmax + BUFFER_DEGREES, ymax + BUFFER_DEGREES)


def main() -> None:
    import geopandas as gpd
    from shapely.geometry import box

    if not HIFLD_SHP.exists():
        log.error("Файл не найден: %s", HIFLD_SHP)
        return

    conn = get_connection()
    try:
        bbox_4326 = get_va_bbox_buffered(conn)
        log.info("VA bbox + буфер (EPSG:4326): %s", bbox_4326)

        # Репроекция bbox в 3857 (CRS источника) для partial-read шейпфайла
        bbox_gdf = gpd.GeoSeries([box(*bbox_4326)], crs="EPSG:4326").to_crs("EPSG:3857")
        bbox_3857 = tuple(bbox_gdf.total_bounds)
        log.info("VA bbox в EPSG:3857 (для partial-read): %s", bbox_3857)

        log.info("Читаю HIFLD-шейпфайл (partial bbox-read)...")
        gdf = gpd.read_file(HIFLD_SHP, bbox=bbox_3857)
        log.info("  Прочитано %d линий в пределах bbox.", len(gdf))

        status_counts = gdf["STATUS"].value_counts().to_dict()
        log.info("  Распределение STATUS в bbox: %s", status_counts)

        gdf = gdf[gdf["STATUS"].isin(ALLOWED_STATUSES)].copy()
        log.info("  После фильтра ALLOWED_STATUSES: %d линий.", len(gdf))

        # Репроекция геометрий в 4326 для хранения
        gdf = gdf.to_crs("EPSG:4326")

        rows = []
        for _, line in gdf.iterrows():
            voltage_raw = line.get("VOLTAGE")
            voltage_kv = None
            try:
                v = float(voltage_raw)
                if v > 0:  # отсекает sentinel -999999.0 и любые отрицательные мусорные значения
                    voltage_kv = v
            except (TypeError, ValueError):
                voltage_kv = None

            geom = line.geometry
            if geom is not None and geom.geom_type == "LineString":
                from shapely.geometry import MultiLineString
                geom = MultiLineString([geom])
            geom_wkt = f"SRID=4326;{geom.wkt}" if geom is not None else None

            raw_attrs = {
                "status_raw": line.get("STATUS"),
                "volt_class_raw": line.get("VOLT_CLASS"),
                "owner": line.get("OWNER"),
                "type": line.get("TYPE"),
                "inferred": line.get("INFERRED"),
                "sub_1": line.get("SUB_1"),
                "sub_2": line.get("SUB_2"),
                "dlr_source_used": False,
                "dlr_skip_reason": (
                    "NREL OEDI 6231: ~19GB/файл HDF5, нецелесообразно для подмножества "
                    "граничных линий VA. thermal_MW определяется через voltage_thermal_lookup "
                    "на этапе compute_gci_v2a_va.py (SPEC §5.1, ветка 'иначе')."
                ),
                "status_filter_decision": (
                    "Включены IN SERVICE и NOT AVAILABLE (NOT AVAILABLE = метаданные не "
                    "заполнены, не отключена). Решение V, см. сессию чата."
                ),
            }

            rows.append(
                (
                    SOURCE,
                    str(line.get("ID")),
                    voltage_kv,
                    None,  # dlr_thermal_mw — не используем DLR
                    geom_wkt,
                    None,  # region_ids[] — заполняется триггером line->region_ids
                    json.dumps(raw_attrs),
                )
            )

        upsert_rows(
            conn,
            table="infrastructure_raw.transmission_lines",
            columns=[
                "source", "source_id", "voltage_kv", "dlr_thermal_mw",
                "geom", "region_ids", "raw_attributes",
            ],
            rows=rows,
            conflict_cols=("source", "source_id"),
        )
    finally:
        conn.close()

    log.info("Готово.")


if __name__ == "__main__":
    main()
