r"""
gci_conus_common.py
======================
Общие утилиты для ТЗ-1 (CONUS base layers).

В отличие от gci_v2a_common.py (M2a) — НИКАКОГО обращения к БД: пайплайн
полностью файловый. core.regions не покрывает CONUS (только VA, 133 строки),
а ТЗ-1 прямо запрещает запись в БД. Границы округов берутся из локального
shapefile, не из Postgres.

Положи этот файл в ту же папку, что и layer-скрипты — они его импортируют.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Подтверждено pre-flight (п.1, п.3): 48 штатов + DC, без AK/HI (EPSG:5070 —
# Conus Albers, для AK/HI нужна отдельная проекция — это и есть тот случай
# "требует отдельной работы", который ТЗ-1 разрешает пропустить).
CONUS_STATES_USPS = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}
CONUS_STATES_FIPS = {
    "01", "04", "05", "06", "08", "09", "10", "11", "12", "13",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25",
    "26", "27", "28", "29", "30", "31", "32", "33", "34", "35",
    "36", "37", "38", "39", "40", "41", "42", "44", "45", "46",
    "47", "48", "49", "50", "51", "53", "54", "55", "56",
}

# Решение зафиксировано в pre-flight: cb 500k, не 5m, не полный TIGER/Line.
BOUNDARY_SHP = Path(r"D:\GISData\Energy\USA\cb_2023_us_county_500k\cb_2023_us_county_500k.shp")
BOUNDARY_SOURCE_NOTE = (
    "Census cartographic boundary cb_2023_us_county_500k (1:500,000). Выбран вместо "
    "5m (слишком генерализован для точной геометрии) и вместо полного TIGER/Line "
    "(юридические границы уходят в воду, напр. Chesapeake Bay — реинтродуцировало бы "
    "offshore-объекты, которых M2a сознательно избегал)."
)

JOIN_CRS = "EPSG:5070"     # Albers Equal Area CONUS — для площади/длины/spatial join
STORAGE_CRS = "EPSG:4326"  # хранение в выходных GeoJSON

OUTPUT_DIR = Path(r"C:\Users\PGS\Documents\AI\AI Buildup Frontier project\data\conus")


def load_conus_counties():
    """
    Границы округов CONUS в JOIN_CRS, колонка 'fips' (= GEOID). Файл сам по
    себе национальный (56 штатов/территорий, проверено pre-flight) — фильтр
    до CONUS_STATES_FIPS применяется здесь, в одном месте, один раз.
    """
    import geopandas as gpd

    if not BOUNDARY_SHP.exists():
        raise FileNotFoundError(
            f"Файл границ не найден: {BOUNDARY_SHP}\n"
            "Скачай https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
        )

    gdf = gpd.read_file(BOUNDARY_SHP)
    gdf = gdf.rename(columns={"GEOID": "fips"})
    gdf = gdf[gdf["STATEFP"].isin(CONUS_STATES_FIPS)].copy()
    gdf = gdf.to_crs(JOIN_CRS)
    log.info("Границы округов CONUS загружены: %d (ожидается 3109)", len(gdf))
    if len(gdf) != 3109:
        log.warning("Количество не совпадает с pre-flight (3109) — проверь фильтр STATEFP.")
    return gdf[["fips", "NAME", "NAMELSAD", "STATEFP", "geometry"]].reset_index(drop=True)


def _is_missing(value: Any) -> bool:
    """Пропуск: None, строка 'NA'/пустая, или pandas/numpy float NaN
    (pandas.read_excel конвертирует текст 'NA' в файле в float NaN, не в
    строку — нужна отдельная проверка, баг был найден в M2a)."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().upper() in ("NA", ""):
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def na_to_none(value: Any) -> Any:
    return None if _is_missing(value) else value


def safe_float(value: Any) -> Optional[float]:
    value = na_to_none(value)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def excel_serial_to_date(serial: Any) -> Optional[dt.date]:
    """Excel serial (напр. 43511) -> date. Пропуски -> None."""
    if _is_missing(serial):
        return None
    if isinstance(serial, dt.datetime):
        return serial.date()
    if isinstance(serial, dt.date):
        return serial
    try:
        return dt.date(1899, 12, 30) + dt.timedelta(days=float(serial))
    except (TypeError, ValueError, OverflowError):
        return None


def resolve_points_to_counties(points_gdf, counties_gdf, fallback_buffer_m: float = 1000.0):
    """
    Двухступенчатое разрешение точка->округ.

    Стадия 1: строгий point-in-polygon (within) — уникальное решение для
    подавляющего большинства точек, без риска задвоения.

    Стадия 2: для точек, не резолвнутых на стадии 1 (обрезка береговой линии
    в cb-границах, международная речная граница) — присваиваем ЕДИНСТВЕННЫЙ
    БЛИЖАЙШИЙ округ, если расстояние <= fallback_buffer_m. Именно ближайший,
    не "любой в буфере вокруг всех округов" — иначе соседние округа начали
    бы перекрываться буферными зонами вдоль обычных сухопутных границ, и
    точки у ЛЮБОЙ межокружной границы (не только берега) задваивались бы.

    Эмпирически откалибровано (generation layer, CONUS): реальные береговые/
    погран-речные случаи — 6-718 м до ближайшего полигона; настоящий офшор
    (Block Island, South Fork Wind, CVOW) — 4865-42758 м. 1000 м с запасом
    разделяет группы в обе стороны.

    Возвращает (joined, n_unresolved). joined — результат sjoin с колонкой
    'fips' (NaN для точек, не резолвленных даже стадией 2).
    """
    import geopandas as gpd

    joined = gpd.sjoin(points_gdf, counties_gdf[["fips", "geometry"]], how="left", predicate="within")
    unresolved_mask = joined["fips"].isna()

    if unresolved_mask.any() and fallback_buffer_m > 0:
        unresolved_idx = joined[unresolved_mask].index
        unresolved_points = points_gdf.loc[unresolved_idx]

        nearest = gpd.sjoin_nearest(
            unresolved_points, counties_gdf[["fips", "geometry"]],
            how="left", distance_col="_dist_m",
        )
        nearest = nearest[~nearest.index.duplicated(keep="first")]  # на случай точной равноудалённости
        within_threshold = nearest["_dist_m"] <= fallback_buffer_m
        fips_to_assign = nearest.loc[within_threshold, "fips"]
        joined.loc[fips_to_assign.index, "fips"] = fips_to_assign.values

    n_unresolved = int(joined["fips"].isna().sum())
    return joined, n_unresolved


def write_layer_outputs(layer_name: str, county_gdf, meta: dict, snapshot_date: str) -> None:
    """
    Единая точка записи для всех 5 слоёв ТЗ-1: CSV + GeoJSON + meta.json.
    county_gdf — GeoDataFrame с колонкой 'fips', атрибутами слоя и geometry
    (геометрия округа, для отображения на карте — не геометрия исходных
    точек/линий). CSV и GeoJSON пишутся из ОДНОГО объекта, чтобы не
    разъехались значения между форматами.

    Ничего не пишет в БД (ТЗ-1 §3 — намеренно).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = OUTPUT_DIR / f"layer_{layer_name}_{snapshot_date}.csv"
    county_gdf.drop(columns="geometry").to_csv(csv_path, index=False)
    log.info("CSV записан: %s (%d строк)", csv_path, len(county_gdf))

    geojson_path = OUTPUT_DIR / f"layer_{layer_name}_{snapshot_date}.geojson"
    county_gdf.to_crs(STORAGE_CRS).to_file(geojson_path, driver="GeoJSON")
    log.info("GeoJSON записан: %s", geojson_path)

    meta = dict(meta)
    meta.setdefault("boundary_source", BOUNDARY_SOURCE_NOTE)
    meta.setdefault("snapshot_date", snapshot_date)
    meta_path = OUTPUT_DIR / f"layer_{layer_name}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    log.info("Meta записан: %s", meta_path)
