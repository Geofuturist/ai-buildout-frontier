r"""
preflight_conus_3_boundary_file.py  (v2 -- цель сменилась на TIGER cb 500k)
=============================================================================
ТЗ-1, pre-flight пункт 3. Решение принято: cartographic boundary 500k, не 5m
и не полный TIGER/Line -- cb-файлы обрезаны по береговой линии, полный
TIGER/Line затянул бы в округа юридические границы над водой (Чесапикский
залив и т.п.) -- ровно то, что M2a сознательно исключал (offshore CVOW и пр.).
Это обоснование пойдёт в метаданные слоя, не только в переписку.

Скачать (11 МБ, подтверждённый прямой URL с census.gov):
    https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip

Распаковать в D:\GISData\Energy\USA\cb_2023_us_county_500k\ (или поправь
BOUNDARY_SHP ниже под свой путь).

Старый 5m-файл (уже на диске) никуда не девается -- он ещё понадобится в
Section 2 для теста чувствительности (VA: 5m vs 500k на новых величинах
max_voltage_kv / км по классам / n_substations).

Запуск (та же папка, тот же способ):
    python preflight_conus_3_boundary_file.py
"""

from __future__ import annotations

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

BOUNDARY_SHP = Path(r"D:\GISData\Energy\USA\cb_2023_us_county_500k\cb_2023_us_county_500k.shp")

INDEPENDENT_CITY_CHECKS = ["Baltimore city", "St. Louis", "St Louis", "Carson City"]


def main() -> None:
    import geopandas as gpd

    if not BOUNDARY_SHP.exists():
        log.error(
            "Файл не найден: %s\nСкачай https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip "
            "и распакуй сюда (или поправь BOUNDARY_SHP в скрипте).",
            BOUNDARY_SHP,
        )
        return

    gdf = gpd.read_file(BOUNDARY_SHP)
    log.info("Колонки (%d): %s", len(gdf.columns), list(gdf.columns))
    log.info("CRS: %s", gdf.crs)
    log.info("Всего features: %d", len(gdf))

    state_col = next((c for c in ("STATEFP", "STATE_FIPS", "STATEFP20", "STATEFP23") if c in gdf.columns), None)
    if state_col:
        log.info("Уникальных штатов (по '%s'): %d", state_col, gdf[state_col].nunique())
    else:
        log.warning("Не нашёл колонку STATEFP-подобную среди: %s", list(gdf.columns))

    name_col = next((c for c in ("NAME", "NAMELSAD", "COUNTY_NAME") if c in gdf.columns), None)
    if name_col:
        log.info("\nПроверка independent cities (поиск по подстроке в '%s'):", name_col)
        for query in INDEPENDENT_CITY_CHECKS:
            matches = gdf[gdf[name_col].str.contains(query, case=False, na=False)]
            if len(matches):
                log.info("  '%s' -> найдено %d: %s", query, len(matches), matches[name_col].tolist()[:5])
            else:
                log.warning("  '%s' -> НЕ найдено", query)
    else:
        log.warning("Не нашёл колонку с именем округа -- не могу проверить independent cities.")

    geoid_col = next((c for c in ("GEOID", "GEOID20", "FIPS", "CNTY_FIPS") if c in gdf.columns), None)
    if geoid_col:
        log.info("\nКолонка FIPS-ключа: '%s'. Примеры: %s", geoid_col, gdf[geoid_col].head(5).tolist())
        lens = gdf[geoid_col].astype(str).str.len().value_counts().to_dict()
        log.info("Длина значений (ожидается 5 для county FIPS): %s", lens)
    else:
        log.warning("Не нашёл GEOID-подобную колонку -- она нужна как ключ join с остальными слоями.")

    log.info("\nРазмер файла на диске: %.1f MB", BOUNDARY_SHP.stat().st_size / 1024**2)

    va = gdf[gdf[state_col] == "51"] if state_col else gdf.iloc[0:0]
    if len(va):
        log.info("\nVA: %d округов в этом файле границ (ожидается 133).", len(va))


if __name__ == "__main__":
    main()
