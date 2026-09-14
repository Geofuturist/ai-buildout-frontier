"""
preflight_conus_2_volumes.py
===============================
ТЗ-1, pre-flight пункты 2 и 5: объёмы по CONUS + полнота координат EIA-860.

НЕ делает spatial join и не пишет никуда. Только подсчёт строк/объектов
после атрибутивных фильтров (Status=='OP', State в CONUS, и т.д.) —
без привязки к округам, это Section 2 "Работа".

Запуск (та же папка, тот же способ):
    python preflight_conus_2_volumes.py
"""

from __future__ import annotations

import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

PLANT_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\2___Plant_Y2024.xlsx")
GENERATOR_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\3_1_Generator_Y2024.xlsx")
HIFLD_SHP = Path(
    r"D:\GISData\Energy\USA\US_Electric_Power_Transmission_Lines_-8378795084787321001"
    r"\Electric_Power_Transmission_Lines_A.shp"
)
BERKELEY_XLSX = Path(r"D:\GISData\Energy\USA\LBNL_Ix_Queue_Data_File_thru2024_v2.xlsx")

# 48 штатов + DC (CONUS). Без AK/HI (см. решение по CRS EPSG:5070 в пре-флайт
# отчёте) и без территорий (PR/VI/GU/AS/MP), которые иногда встречаются в EIA-860.
CONUS_STATES = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


def check_eia860() -> None:
    import pandas as pd

    log.info("=" * 78)
    log.info("EIA-860 — объём и координаты, CONUS")
    log.info("=" * 78)
    if not PLANT_XLSX.exists() or not GENERATOR_XLSX.exists():
        log.error("Не найден один из файлов EIA-860.")
        return

    t0 = time.time()
    plant_df = pd.read_excel(PLANT_XLSX, sheet_name="Plant", header=1)
    gen_df = pd.read_excel(GENERATOR_XLSX, sheet_name="Operable", header=1)
    log.info("  Чтение заняло %.1f сек.", time.time() - t0)

    log.info("  Generator 'Operable' всего строк (все штаты/территории): %d", len(gen_df))
    log.info("  Уникальные 'State' в Generator: %s", sorted(gen_df["State"].dropna().unique()))
    log.info("  Уникальные 'Status' в Generator: %s", sorted(gen_df["Status"].dropna().unique()))

    conus_op = gen_df[(gen_df["State"].isin(CONUS_STATES)) & (gen_df["Status"] == "OP")].copy()
    log.info("  CONUS + Status=='OP': %d генераторов", len(conus_op))

    plant_lookup = plant_df.set_index("Plant Code")[["Latitude", "Longitude", "State"]]
    merged = conus_op.join(plant_lookup, on="Plant Code", rsuffix="_plant")

    # Векторно, без построчного .apply() — на VA (696 строк) разницы не видно,
    # на CONUS+OP (на порядок больше строк) построчный apply() ощутимо тормозит.
    lat = pd.to_numeric(merged["Latitude"], errors="coerce")
    lon = pd.to_numeric(merged["Longitude"], errors="coerce")
    valid_mask = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
    n_valid = int(valid_mask.sum())
    n_total = len(merged)
    log.info(
        "  С валидными координатами: %d/%d (%.1f%%)",
        n_valid, n_total, 100 * n_valid / n_total if n_total else 0,
    )
    if n_total - n_valid > 0:
        bad = merged[~valid_mask]
        log.warning(
            "  Без координат/битые (%d) — распределение по State: %s",
            len(bad), bad["State"].value_counts().to_dict(),
        )


def check_hifld() -> None:
    import geopandas as gpd

    log.info("\n" + "=" * 78)
    log.info("HIFLD Transmission Lines — объём, CONUS (нац. файл, без bbox)")
    log.info("=" * 78)
    if not HIFLD_SHP.exists():
        log.error("Файл не найден: %s", HIFLD_SHP)
        return

    t0 = time.time()
    gdf = gpd.read_file(HIFLD_SHP)
    elapsed = time.time() - t0
    log.info("  Прочитано %d линий (весь нац. файл) за %.1f сек.", len(gdf), elapsed)

    log.info("  Распределение STATUS (нац.): %s", gdf["STATUS"].value_counts().to_dict())
    n_allowed = len(gdf[gdf["STATUS"].isin({"IN SERVICE", "NOT AVAILABLE"})])
    log.info("  После фильтра IN SERVICE + NOT AVAILABLE: %d", n_allowed)
    log.info("  Bounds геометрии (исходный CRS %s): %s", gdf.crs, tuple(gdf.total_bounds))


def check_berkeley() -> None:
    import pandas as pd

    log.info("\n" + "=" * 78)
    log.info("LBNL Queued Up — объём, национально (все ISO/BA)")
    log.info("=" * 78)
    if not BERKELEY_XLSX.exists():
        log.error("Файл не найден: %s", BERKELEY_XLSX)
        return

    t0 = time.time()
    df = pd.read_excel(BERKELEY_XLSX, sheet_name="03. Complete Queue Data", header=1)
    log.info("  Чтение заняло %.1f сек. Всего строк: %d", time.time() - t0, len(df))

    log.info("  q_status value_counts (нац.): %s", df["q_status"].value_counts().to_dict())
    log.info("  region (ISO/BA) value_counts (нац.): %s", df["region"].value_counts().to_dict())

    n_active = len(df[df["q_status"] == "active"])
    log.info("  status=='active' (нац., все ISO/BA): %d", n_active)

    n_fips_ok = int(df["fips_codes"].notna().sum())
    log.info("  С непустым fips_codes: %d/%d (%.1f%%)", n_fips_ok, len(df), 100 * n_fips_ok / len(df))


if __name__ == "__main__":
    check_eia860()
    check_hifld()
    check_berkeley()
