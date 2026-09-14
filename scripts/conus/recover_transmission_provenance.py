"""
recover_transmission_provenance.py
=====================================
RES, условие 4: восстановить максимум о происхождении/vintage файла
HIFLD Transmission Lines, раз канал+дата скачивания не вспоминаются.

Три независимых источника сигнала:
  1. OS-метаданные файлов на диске (.zip и распакованный .shp) — когда
     файл появился/менялся на ЭТОЙ машине (не то же самое, что "когда
     скачан из интернета", но ближайший доступный proxy).
  2. Внутренние timestamp'ы записей ВНУТРИ .zip-архива — серверные
     экспорты ArcGIS Hub часто проставляют реальное время генерации
     экспорта в архиве, это может быть точнее OS-даты файла.
  3. Атрибутивные поля SOURCEDATE / VAL_DATE — они per-line, не
     dataset-level, но их max() по всем записям — честный сигнал
     "насколько свежие данные легли в основу файла", независимо от
     того, когда именно он был скачан.

Ничего не выдумывает: если какой-то сигнал недоступен — пишет об этом
явно, а не подставляет правдоподобное значение.

Запуск (та же папка, тот же способ):
    python recover_transmission_provenance.py
"""

from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ZIP_PATH = Path(r"D:\GISData\Energy\GEM\US_Electric_Power_Transmission_Lines_-8378795084787321001.zip")
SHP_DIR = Path(r"D:\GISData\Energy\USA\US_Electric_Power_Transmission_Lines_-8378795084787321001")
SHP_PATH = SHP_DIR / "Electric_Power_Transmission_Lines_A.shp"


def report_os_dates(path: Path, label: str) -> None:
    if not path.exists():
        log.warning("  %s: файл/папка не найдена (%s)", label, path)
        return
    stat = path.stat()
    log.info(
        "  %s: created=%s, modified=%s",
        label,
        datetime.fromtimestamp(stat.st_ctime).isoformat(),
        datetime.fromtimestamp(stat.st_mtime).isoformat(),
    )


def report_zip_internals() -> None:
    log.info("=" * 78)
    log.info("1. OS-даты .zip и распакованных файлов")
    log.info("=" * 78)
    report_os_dates(ZIP_PATH, "zip-архив")
    report_os_dates(SHP_DIR, "распакованная папка")
    for ext in (".shp", ".dbf", ".shx", ".prj"):
        report_os_dates(SHP_PATH.with_suffix(ext), f"  .{ext.lstrip('.')}")

    log.info("\n" + "=" * 78)
    log.info("2. Внутренние timestamp'ы записей ВНУТРИ .zip (если архив сохранился)")
    log.info("=" * 78)
    if not ZIP_PATH.exists():
        log.warning("  Архив не найден на диске — этот сигнал недоступен.")
        return
    try:
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            for info in zf.infolist():
                dt = datetime(*info.date_time)
                log.info("  %-60s  внутренняя дата: %s", info.filename, dt.isoformat())
    except zipfile.BadZipFile:
        log.warning("  Файл повреждён или не является валидным zip — сигнал недоступен.")


def report_attribute_dates() -> None:
    log.info("\n" + "=" * 78)
    log.info("3. Распределение SOURCEDATE / VAL_DATE по ВСЕМ записям (не первые 5)")
    log.info("=" * 78)
    if not SHP_PATH.exists():
        log.warning("  .shp не найден — сигнал недоступен.")
        return

    import geopandas as gpd
    import pandas as pd

    gdf = gpd.read_file(SHP_PATH)
    log.info("  Всего записей: %d", len(gdf))

    for field in ("SOURCEDATE", "VAL_DATE"):
        if field not in gdf.columns:
            log.warning("  Поле %s отсутствует в схеме — сигнал недоступен.", field)
            continue
        series = pd.to_datetime(gdf[field], errors="coerce")
        n_valid = series.notna().sum()
        n_total = len(series)
        if n_valid == 0:
            log.warning("  %s: ни одного валидного значения даты (%d/%d) — сигнал недоступен.", field, n_valid, n_total)
            continue
        log.info(
            "  %s: valid=%d/%d (%.1f%%), min=%s, max=%s, median=%s",
            field, n_valid, n_total, 100 * n_valid / n_total,
            series.min().date(), series.max().date(), series.median().date(),
        )


def main() -> None:
    report_zip_internals()
    report_attribute_dates()
    log.info("\n" + "=" * 78)
    log.info(
        "ИТОГ для метаданных слоя: используем максимум из найденного выше как snapshot_date, "
        "с явной пометкой 'канал скачивания не восстановлен — определено по локальным файловым "
        "и атрибутивным данным'. Если выше везде warning — так и пишем в meta.json, не подставляем "
        "правдоподобную дату."
    )


if __name__ == "__main__":
    main()
