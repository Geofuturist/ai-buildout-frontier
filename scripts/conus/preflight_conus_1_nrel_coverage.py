"""
preflight_conus_1_nrel_coverage.py
=====================================
TЗ-1, pre-flight пункт 1: покрытие NREL OEDI 8562 по CONUS.

Читает ТОЛЬКО список колонок (структуру), не данные целиком — это быстро
даже для Fixed-формата HDFStore (store.select с stop=0), как и в M2a.

Запуск (та же папка, тот же способ):
    python preflight_conus_1_nrel_coverage.py
"""

from __future__ import annotations

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

NREL_H5 = Path(r"D:\GISData\Energy\USA\historic_load_hourly_2016_2023_county.h5")

# Стандартные 2-значные FIPS коды штатов — справочные, статичные данные.
STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}
CONUS_FIPS = {k for k in STATE_FIPS if k not in ("02", "15")}  # искл. Alaska, Hawaii


def main() -> None:
    import pandas as pd

    if not NREL_H5.exists():
        log.error("Файл не найден: %s", NREL_H5)
        return

    store = pd.HDFStore(str(NREL_H5), mode="r")
    try:
        cols = store.select("/data", start=0, stop=0).columns
    finally:
        store.close()

    log.info("Всего колонок в файле: %d", len(cols))

    county_fips_present = set()
    malformed = []
    for c in cols:
        if not c.startswith("p") or len(c) != 6:
            malformed.append(c)
            continue
        county_fips_present.add(c[1:])

    if malformed:
        log.warning("Колонки НЕ в формате 'p'+5digit (%d шт.): %s", len(malformed), malformed[:20])

    state_fips_present = {f[:2] for f in county_fips_present}

    log.info("Уникальных county-FIPS: %d", len(county_fips_present))
    log.info("Уникальных штатов (по префиксу): %d", len(state_fips_present))

    missing_conus = CONUS_FIPS - state_fips_present
    extra = state_fips_present - set(STATE_FIPS.keys())

    if missing_conus:
        log.warning(
            "ОТСУТСТВУЮТ CONUS-штаты (ожидается 48+DC): %s",
            {STATE_FIPS.get(f, f): f for f in sorted(missing_conus)},
        )
    else:
        log.info("Все 48 штатов CONUS + DC присутствуют.")

    log.info(
        "Alaska (02) в файле: %s | Hawaii (15) в файле: %s",
        "02" in state_fips_present, "15" in state_fips_present,
    )
    if extra:
        log.info("Коды вне справочника STATE_FIPS (территории/мусор?): %s", extra)

    log.info("\nСчётчик county-FIPS по штату (CONUS, для сверки со Script 3):")
    for fips_code in sorted(CONUS_FIPS):
        n = sum(1 for f in county_fips_present if f.startswith(fips_code))
        log.info("  %-4s (%s): %d округов", STATE_FIPS[fips_code], fips_code, n)


if __name__ == "__main__":
    main()
