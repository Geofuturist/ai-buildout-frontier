r"""
build_layer_demand_nrel.py
=============================
ТЗ-1, слой 2/5: peak_demand_mw по округу, CONUS.
NREL/NLR OEDI submission 8562 -- почасовой спрос по округам, 2016-2023.

Никакого spatial join -- колонки файла уже 'p'+FIPS, pre-flight (скрипт 1)
подтвердил все 3109 округов CONUS на месте, AK/HI в файле отсутствуют сами
по себе. peak_demand_mw = годовой почасовой максимум за 2023 (залочено,
как и в M2a -- единственный год, max(summer,winter) операционально = annual
max).

Файл в Fixed-формате HDFStore (подтверждено в M2a) -- партиционное чтение
(columns=/where=) не поддержано, читаем целиком (~1.7 ГБ, пара секунд по
факту на этой машине).

Запуск (та же папка, что и gci_conus_common.py):
    python build_layer_demand_nrel.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from gci_conus_common import load_conus_counties, write_layer_outputs, log

NREL_H5 = Path(r"D:\GISData\Energy\USA\historic_load_hourly_2016_2023_county.h5")
LAYER_NAME = "demand_nrel8562"
SOURCE_URL = "https://data.openei.org/submissions/8562"
NREL_YEAR = 2023


def main() -> None:
    import pandas as pd
    import geopandas as gpd

    if not NREL_H5.exists():
        log.error("Файл не найден: %s", NREL_H5)
        return

    log.info("Читаю NREL H5 целиком (Fixed-формат, partial select не поддержан)...")
    store = pd.HDFStore(str(NREL_H5), mode="r")
    try:
        df_full = store["/data"]
    finally:
        store.close()
    log.info("Прочитано: %s", df_full.shape)

    df_year = df_full.loc[f"{NREL_YEAR}-01-01":f"{NREL_YEAR}-12-31"]
    log.info("Строк за %d год: %d", NREL_YEAR, len(df_year))
    del df_full

    peak = df_year.max(axis=0)
    peak.index = [c[1:] if c.startswith("p") else c for c in peak.index]  # 'p51001' -> '51001'
    peak_df = peak.rename("peak_demand_mw").reset_index().rename(columns={"index": "fips"})

    counties = load_conus_counties()
    result = counties.merge(peak_df, on="fips", how="left")

    n_missing = result["peak_demand_mw"].isna().sum()
    if n_missing:
        missing_fips = result.loc[result["peak_demand_mw"].isna(), "fips"].tolist()
        log.warning("%d округов CONUS без данных в NREL-файле: %s", n_missing, missing_fips)

    snapshot_date = dt.date.today().strftime("%Y%m%d")
    meta = {
        "source": "NREL/NLR OEDI submission 8562 — Hourly Electricity Demand Profiles for US Counties",
        "source_url": SOURCE_URL,
        "vintage": f"почасовые данные 2016-2023, взят год {NREL_YEAR}",
        "license": "см. страницу OEDI submission 8562 (открытый доступ, без регистрации)",
        "coverage": "48 states + DC (CONUS) — AK/HI отсутствуют в самом источнике",
        "n_units_covered": int(result["peak_demand_mw"].notna().sum()),
        "n_units_no_data": int(n_missing),
        "known_gaps": (
            f"peak_demand_mw = годовой почасовой максимум за {NREL_YEAR} год (единственный залоченный "
            "год, как и в пилоте M2a по Вирджинии). Не включает существующую DC-нагрузку отдельным "
            "слагаемым (в отличие от старой Peak_adj из M2a v1) — это чистый спрос по счётчикам "
            "коммунальных сетей, без derived-поправок."
        ),
    }

    write_layer_outputs(
        LAYER_NAME,
        result[["fips", "NAME", "NAMELSAD", "peak_demand_mw", "geometry"]],
        meta,
        snapshot_date,
    )
    log.info("ГОТОВО.")


if __name__ == "__main__":
    main()
