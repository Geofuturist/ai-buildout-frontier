r"""
build_layer_transmission_lines_hifld.py
==========================================
ТЗ-1, слой 3/5: transmission lines, CONUS. Редизайн по решению RES: НЕ
публикуем boundary_thermal_mw/import_proxy/inbound_thermal_sum (см. чат --
import_proxy коррелировал со спросом на 0.9995, это была переименованная
копия demand, а не новая информация). Вместо этого:

  1. Сырая геометрия линий (voltage_kv, class), БЕЗ агрегации -- отдельный
     GeoJSON, это основной слой трансмиссии.
  2. County-уровень через "вложенность" (intersects с ПЛОЩАДЬЮ округа), не
     пересечение с линией границы -- устойчивее к генерализованной
     геометрии (линия вдоль границы не переворачивается от километрового
     сдвига, как было с пересечением границы в M2a):
       - max_voltage_kv -- дёшево, обычный sjoin(predicate='intersects')
       - km_<voltage_class> -- дороже, geometric overlay (реальный клип
         геометрии по полигону округа), км ЦЕЛЫМИ (геометрия HIFLD не
         геодезической точности, дробить дальше -- ложная точность)

STATUS-фильтр: IN SERVICE + NOT AVAILABLE (решение V, см. чат -- NOT
AVAILABLE = метаданные не заполнены, не "выведена из эксплуатации").
CONUS-фильтр: грубый bbox по границам counties (Аляска/Гавайи/территории --
разница в тысячи км, точность тут не нужна).

Provenance файла (см. recover_transmission_provenance.py): дата экспорта
zip на источнике -- 2026-02-26 (внутренние timestamp'ы архива); канал/URL
скачивания НЕ восстановлен. SOURCEDATE/VAL_DATE по записям -- до 2024-09-26.

Запуск (та же папка, что и gci_conus_common.py):
    python build_layer_transmission_lines_hifld.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from gci_conus_common import load_conus_counties, write_layer_outputs, OUTPUT_DIR, JOIN_CRS, STORAGE_CRS, log

HIFLD_SHP = Path(
    r"D:\GISData\Energy\USA\US_Electric_Power_Transmission_Lines_-8378795084787321001"
    r"\Electric_Power_Transmission_Lines_A.shp"
)

LAYER_NAME = "transmission_lines_hifld"
SOURCE_URL = "https://gii.dhs.gov/HIFLD"
SNAPSHOT_DATE_SOURCE = "2026-02-26"
DATA_VINTAGE_NOTE = "SOURCEDATE/VAL_DATE по записям: до 2024-09-26 (max по всем 94619 записям)"

ALLOWED_STATUSES = {"IN SERVICE", "NOT AVAILABLE"}

# (порог kV снизу, метка класса) -- проверяются по убыванию порога
VOLTAGE_CLASS_BOUNDARIES = [
    (765, "ge765"), (500, "v500"), (345, "v345"), (230, "v230"),
    (138, "v138"), (115, "v115"), (69, "v69"),
]


def classify_voltage(v) -> str:
    if v is None:
        return "lt69_unknown"
    for threshold, label in VOLTAGE_CLASS_BOUNDARIES:
        if v >= threshold:
            return label
    return "lt69_unknown"  # покрывает NaN (падает через все сравнения) и v<69


def main() -> None:
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import box

    log.info("Читаю HIFLD Transmission Lines (нац. файл)...")
    gdf = gpd.read_file(HIFLD_SHP)
    log.info("Прочитано %d линий всего.", len(gdf))

    gdf = gdf[gdf["STATUS"].isin(ALLOWED_STATUSES)].copy()
    log.info("После фильтра STATUS (IN SERVICE + NOT AVAILABLE): %d", len(gdf))

    voltage_raw = pd.to_numeric(gdf["VOLTAGE"], errors="coerce")
    gdf["voltage_kv"] = voltage_raw.where(voltage_raw > 0)  # sentinel -999999 -> NaN
    gdf["voltage_class"] = gdf["voltage_kv"].apply(classify_voltage)

    gdf = gdf.to_crs(JOIN_CRS)

    counties = load_conus_counties()

    minx, miny, maxx, maxy = counties.total_bounds
    conus_bbox = box(minx, miny, maxx, maxy)
    gdf_conus = gdf[gdf.geometry.intersects(conus_bbox)].copy()
    log.info("После грубого CONUS bbox-фильтра: %d (было %d нац.)", len(gdf_conus), len(gdf))

    snapshot_date = dt.date.today().strftime("%Y%m%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Пишу сырую геометрию линий (без агрегации)...")
    raw_path = OUTPUT_DIR / f"layer_{LAYER_NAME}_segments_{snapshot_date}.geojson"
    cols_raw = ["ID", "STATUS", "voltage_kv", "voltage_class", "OWNER", "geometry"]
    gdf_conus[cols_raw].to_crs(STORAGE_CRS).to_file(raw_path, driver="GeoJSON")
    log.info("Сырая геометрия записана: %s (%d объектов)", raw_path, len(gdf_conus))

    log.info("sjoin (intersects) для max_voltage_kv...")
    joined = gpd.sjoin(
        gdf_conus[["voltage_kv", "geometry"]], counties[["fips", "geometry"]],
        how="inner", predicate="intersects",
    )
    has_any_line_fips = set(joined["fips"].unique())  # геометрический факт, не зависит от voltage_kv
    max_v = joined.groupby("fips")["voltage_kv"].max().rename("max_voltage_kv")

    log.info("overlay (геометрический клип) для км по классам напряжения — может занять время...")
    t0 = dt.datetime.now()
    clipped = gpd.overlay(
        gdf_conus[["voltage_class", "geometry"]], counties[["fips", "geometry"]],
        how="intersection",
    )
    elapsed = (dt.datetime.now() - t0).total_seconds()
    log.info("overlay готов за %.1f сек, %d фрагментов", elapsed, len(clipped))

    clipped["length_km"] = clipped.geometry.length / 1000.0
    by_class = clipped.groupby(["fips", "voltage_class"])["length_km"].sum().round(0).astype(int)
    km_wide = by_class.unstack(fill_value=0)
    km_wide.columns = [f"km_{c}" for c in km_wide.columns]

    result = counties.merge(max_v, on="fips", how="left").merge(km_wide, on="fips", how="left")
    km_cols = [c for c in result.columns if c.startswith("km_")]
    result[km_cols] = result[km_cols].fillna(0).astype(int)

    result["has_any_line"] = result["fips"].isin(has_any_line_fips)

    total_km = result[km_cols].sum(axis=1)
    unknown_km = result["km_lt69_unknown"] if "km_lt69_unknown" in result.columns else 0
    result["frac_km_unknown_voltage"] = (unknown_km / total_km).where(total_km > 0)

    n_no_lines_at_all = int((~result["has_any_line"]).sum())
    n_lines_unknown_voltage_only = int(
        (result["has_any_line"] & result["max_voltage_kv"].isna()).sum()
    )
    log.info("Округов БЕЗ единой линии в пределах (геометрически): %d/%d", n_no_lines_at_all, len(result))
    log.info(
        "Округов с линией(-ями), но неизвестным voltage у ВСЕХ них: %d/%d",
        n_lines_unknown_voltage_only, len(result),
    )

    meta = {
        "source": "HIFLD Transmission Lines (nationwide feature class)",
        "source_url": SOURCE_URL,
        "vintage": (
            f"экспорт архива: {SNAPSHOT_DATE_SOURCE} (восстановлено из внутренних timestamp'ов zip — "
            f"канал/URL скачивания НЕ восстановлен, см. отдельный provenance-отчёт); {DATA_VINTAGE_NOTE}"
        ),
        "license": "публичные данные HIFLD/DHS; вопросы условий использования — hifld@hq.dhs.gov",
        "coverage": "48 states + DC (CONUS)",
        "n_units_covered": int(len(gdf_conus)),
        "n_units_no_data": n_no_lines_at_all,
        "known_gaps": (
            f"{n_no_lines_at_all} округов геометрически не содержат ни одной линии этого статуса "
            "(проверено вручную: 4 независимых города Вирджинии — маленькие полигоны; 2 острова — "
            "Nantucket, Dukes County/Martha's Vineyard; 6 сельских малонаселённых округов Джорджии, "
            "Вирджинии, Пенсильвании, Айовы — расстояние до ближайшей линии везде километры-десятки "
            f"км, не геометрический промах). Отдельно {n_lines_unknown_voltage_only} округов ИМЕЮТ "
            "линию(и) в пределах, но voltage_kv неизвестен у всех — max_voltage_kv для них NaN, это "
            "не 'нет линий', см. поле has_any_line и frac_km_unknown_voltage по каждому округу. "
            "max_voltage_kv/км по классам считаются через 'вложенность' (intersects с площадью "
            "округа), не пересечение с линией границы. thermal MW не публикуется вообще — осознанное "
            "решение, не пробел. Км округлены до целого."
        ),
    }

    write_layer_outputs(
        LAYER_NAME,
        result[["fips", "NAME", "NAMELSAD", "max_voltage_kv", "has_any_line", "frac_km_unknown_voltage"]
               + km_cols + ["geometry"]],
        meta,
        snapshot_date,
    )
    log.info("ГОТОВО.")


if __name__ == "__main__":
    main()
