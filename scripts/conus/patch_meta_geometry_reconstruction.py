r"""
patch_meta_geometry_reconstruction.py
========================================
Разовый патч уже существующих 5 meta.json -- добавляет поле
'geometry_reconstruction' (как получить geojson, раз он не в git). Не
трогает layer_transmission_lines_hifld_segments -- для него это
неприменимо (см. recreate_layer_geojson.py). НЕ требует повторного прогона
build_layer_* (substations уже стоил 4 часа и множества попыток).

Запуск (та же папка, что и gci_conus_common.py):
    python patch_meta_geometry_reconstruction.py
"""

import json
from pathlib import Path

CONUS_DIR = Path(r"C:\Users\PGS\Documents\AI\AI Buildup Frontier project\data\conus")

LAYERS = ["generation_eia860", "demand_nrel8562", "transmission_lines_hifld", "substations_osm", "queue_lbnl"]

NOTE_TEMPLATE = (
    "GeoJSON не хранится в git (производная величина, восстанавливается детерминированно): "
    "python recreate_layer_geojson.py {layer} -- берёт актуальный layer_{layer}_<дата>.csv "
    "и cb_2023_us_county_500k.shp, join по fips."
)


def main() -> None:
    for layer in LAYERS:
        meta_path = CONUS_DIR / f"layer_{layer}_meta.json"
        if not meta_path.exists():
            print(f"НЕ НАЙДЕН: {meta_path}")
            continue
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
        meta["geometry_reconstruction"] = NOTE_TEMPLATE.format(layer=layer)
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2, ensure_ascii=False)
        print(f"Обновлён: {meta_path.name}")

    print(
        "\nlayer_transmission_lines_hifld_segments НЕ тронут -- геометрия там и есть "
        "содержание, из CSV не восстанавливается. Путь читателя к сырым линиям (raw "
        "geojson рядом с pmtiles на R2, или только тайлы) -- решает Архитектор."
    )


if __name__ == "__main__":
    main()
