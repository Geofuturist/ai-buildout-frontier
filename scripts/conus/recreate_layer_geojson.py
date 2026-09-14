r"""
recreate_layer_geojson.py
============================
Восстанавливает GeoJSON слоя из CSV + файла границ округов
(cb_2023_us_county_500k). GeoJSON НЕ хранится в git (data\conus\*.geojson
в .gitignore) -- производная величина, восстанавливается детерминированно
за секунды. Git хранит рецепт (этот скрипт + CSV + файл границ), не сам
результат (решение RES).

НЕ применимо к layer_transmission_lines_hifld_segments -- там геометрия
И ЕСТЬ содержание (атрибутов почти нет), из county-CSV не восстанавливается.
Этот подслой в git не идёт вообще, путь -- в pmtiles (Tippecanoe -> R2).

Запуск (та же папка, что и gci_conus_common.py):
    python recreate_layer_geojson.py generation_eia860
    python recreate_layer_geojson.py --all
"""

from __future__ import annotations

import sys
from pathlib import Path

from gci_conus_common import load_conus_counties, OUTPUT_DIR, STORAGE_CRS, log

LAYERS = ["generation_eia860", "demand_nrel8562", "transmission_lines_hifld", "substations_osm", "queue_lbnl"]


def find_latest_csv(layer: str) -> Path | None:
    matches = sorted(OUTPUT_DIR.glob(f"layer_{layer}_*.csv"))
    return matches[-1] if matches else None


def recreate(layer: str) -> None:
    import pandas as pd
    import geopandas as gpd

    csv_path = find_latest_csv(layer)
    if csv_path is None:
        log.error("Не найден CSV для слоя '%s' в %s", layer, OUTPUT_DIR)
        return

    log.info("Восстанавливаю geojson для '%s' из %s", layer, csv_path.name)
    df = pd.read_csv(csv_path, dtype={"fips": str})
    counties = load_conus_counties().to_crs(STORAGE_CRS)

    merged = df.merge(counties[["fips", "geometry"]], on="fips", how="left")
    result = gpd.GeoDataFrame(merged, geometry="geometry", crs=STORAGE_CRS)

    geojson_path = csv_path.with_suffix(".geojson")
    result.to_file(geojson_path, driver="GeoJSON")
    log.info("Записано: %s (%d объектов)", geojson_path, len(result))


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Использование: python {Path(__file__).name} <layer_name>|--all")
        print(f"Доступные слои: {', '.join(LAYERS)}")
        return

    arg = sys.argv[1]
    if arg == "--all":
        for layer in LAYERS:
            recreate(layer)
    elif arg in LAYERS:
        recreate(arg)
    else:
        print(f"Неизвестный слой: {arg}")
        print(f"Доступные: {', '.join(LAYERS)}")


if __name__ == "__main__":
    main()
