"""
gci_v2a_common.py
====================
Общие утилиты для всех ingestion-скриптов Milestone 2a:
- подключение к Supabase (psycopg2) через переменную окружения DATABASE_URL
- загрузка маппинга FIPS -> region_id из core.regions (133 county-equivalents VA)
- конвертация Excel-serial дат
- UPSERT-хелпер по (source, source_id)

Перед запуском любого ingestion-скрипта установи переменную окружения:

    Windows PowerShell:
        $env:DATABASE_URL = "postgresql://postgres.xxxx:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres"

    Windows CMD:
        set DATABASE_URL=postgresql://postgres.xxxx:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres

Строку подключения берёшь в Supabase: Project Settings -> Database ->
Connection string -> "Transaction pooler" (порт 6543, IPv4-совместимый,
рекомендуется для скриптов с большим числом коротких соединений) либо
"Session pooler" (порт 5432) — оба подходят для этого ingestion-объёма.

НЕ хардкодь пароль в файлах скриптов — только через переменную окружения.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
from typing import Any, Iterable, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

JOIN_CRS = "EPSG:5070"      # Albers Equal Area, метры — для всех spatial join (RES_return §2.0)
STORAGE_CRS = "EPSG:4326"   # хранение в БД


def get_connection():
    """Открывает psycopg2-соединение по DATABASE_URL из окружения."""
    try:
        import psycopg2
    except ImportError:
        log.error("psycopg2 не установлен. Выполни: python -m pip install psycopg2-binary")
        sys.exit(1)

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log.error(
            "Переменная окружения DATABASE_URL не задана.\n"
            "  PowerShell: $env:DATABASE_URL = \"postgresql://...\"\n"
            "  CMD:        set DATABASE_URL=postgresql://...\n"
            "Строку подключения возьми в Supabase: Project Settings -> Database -> Connection string."
        )
        sys.exit(1)

    conn = psycopg2.connect(dsn)
    log.info("Подключение к БД установлено.")
    return conn


def load_va_fips_region_map(conn) -> dict[str, str]:
    """
    Возвращает {fips_5digit: region_id} для всех 133 VA county-equivalents.
    fips_5digit — строка вида '51001' (admin_code из core.regions, без префиксов).
    """
    with conn.cursor() as cur:
        cur.execute(
            "select admin_code, id::text from core.regions "
            "where country_code = 'US' and admin_code like '51%'"
        )
        rows = cur.fetchall()
    mapping = {admin_code: region_id for admin_code, region_id in rows}
    log.info("Загружено %d VA region-маппингов (FIPS -> region_id).", len(mapping))
    if len(mapping) != 133:
        log.warning(
            "Ожидалось 133 county-equivalents VA, получено %d — проверь core.regions.",
            len(mapping),
        )
    return mapping


def _is_missing(value: Any) -> bool:
    """True для None, строки 'NA'/пустой строки, а также pandas/numpy float NaN
    (pandas.read_excel по умолчанию конвертирует текст 'NA' в самой книге
    в float NaN — не в строку 'NA' — отсюда нужна отдельная проверка)."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().upper() in ("NA", ""):
        return True
    if isinstance(value, float):
        import math
        if math.isnan(value):
            return True
    return False


def excel_serial_to_date(serial: Any) -> Optional[dt.date]:
    """
    Конвертирует Excel serial-число (как в Berkeley Queued Up, напр. 43511)
    в date. Пропуски (None / 'NA' / NaN) -> None.
    Excel epoch: 1899-12-30 (учитывает фантомный день 1900-02-29 как в Excel).
    """
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


def na_to_none(value: Any) -> Any:
    """Пропуски (строка 'NA' ИЛИ pandas float NaN) -> None."""
    return None if _is_missing(value) else value


def safe_float(value: Any) -> Optional[float]:
    value = na_to_none(value)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def upsert_rows(
    conn,
    table: str,
    columns: list[str],
    rows: Iterable[tuple],
    conflict_cols: tuple[str, ...] = ("source", "source_id"),
    batch_size: int = 500,
) -> int:
    """
    Идемпотентный UPSERT через execute_values, ON CONFLICT DO UPDATE.
    Конвенция M1/ARCHITECTURE_DECISIONS §4.6: UPSERT по (source, source_id).
    Возвращает количество обработанных строк.
    """
    from psycopg2.extras import execute_values

    rows = list(rows)
    if not rows:
        log.warning("Нет строк для UPSERT в %s.", table)
        return 0

    update_cols = [c for c in columns if c not in conflict_cols]
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
    conflict_clause = ", ".join(conflict_cols)

    sql = (
        f"insert into {table} ({', '.join(columns)}) values %s "
        f"on conflict ({conflict_clause}) do update set {set_clause}, updated_at = now()"
    )

    total = 0
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            execute_values(cur, sql, batch)
            total += len(batch)
            log.info("  UPSERT %s: %d/%d строк...", table, total, len(rows))
    conn.commit()
    log.info("UPSERT в %s завершён: %d строк.", table, total)
    return total
