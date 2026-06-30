"""
compute_gci_v2a_va.py
========================
Вычисляет сырые оси 1-3 GCI v2.0 по 133 county-equivalents Virginia.
SPEC_GCI_v2_0_M2a_pipeline.md §5, §7.

НЕ пишет в indices.grid_constraint (это milestone 2b). НЕ считает категории/
пороги/confidence. Выход — CSV + params_used.json, калибровочный вход для 2b.

Источники (уже должны быть загружены в БД ingestion-скриптами):
  - infrastructure_raw.power_plants      (EIA-860)
  - infrastructure_raw.transmission_lines (HIFLD)
  - infrastructure_raw.interconnection_queue (Berkeley)
  - infrastructure_raw.dc_inventory      (VA DEQ)
Плюс локальный файл NREL OEDI 8562 (Peak_adj, не в БД — слишком большой,
читается напрямую отсюда).

Запуск:
    python compute_gci_v2a_va.py
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from gci_v2a_common import get_connection, log

NREL_H5 = Path(r"D:\GISData\Energy\USA\historic_load_hourly_2016_2023_county.h5")
OUTPUT_DIR = Path(r"C:\Users\PGS\Documents\AI\AI Buildup Frontier project\data")

# --- Параметры (залочены, SPEC §6) ------------------------------------------
PARAMS = {
    "transmission_derating_factor": 0.50,
    "import_cap_pct": 0.50,
    "dc_backup_gen_to_load_factor": 0.70,  # multiply, load = 0.70 * genset_nameplate
    "completion_rate_by_iso": {"PJM": 0.13},  # provisional capacity-weighted; финальная калибровка — 2b
    "nrel_year": 2023,
    "eia860_year": 2024,
    "voltage_thermal_lookup_mw": {
        "ge765": 2400, "v500": 1500, "v345": 900, "v230": 400,
        "v138": 150, "v115": 120, "v69": 50, "lt69_unknown": 25,
    },
    "hifld_status_filter": "IN SERVICE + NOT AVAILABLE (см. решение V в сессии чата)",
    "dlr_used": False,
}

SANITY_CHECK_FIPS = {"51107": "Loudoun", "51153": "Prince William", "51059": "Fairfax County"}


# --- SQL: агрегации по округам -----------------------------------------------

SQL_REGIONS = """
select admin_code as fips, id::text as region_id, name as county_name
from core.regions
where country_code = 'US' and admin_code like '51%%'
order by admin_code;
"""

SQL_AXIS1_LINES = """
with line_thermal as (
  select
    tl.id, tl.geom, tl.voltage_kv, tl.raw_attributes,
    case
      when tl.voltage_kv is null or tl.voltage_kv <= 0 then 25
      when tl.voltage_kv >= 765 then 2400
      when tl.voltage_kv >= 500 then 1500
      when tl.voltage_kv >= 345 then 900
      when tl.voltage_kv >= 230 then 400
      when tl.voltage_kv >= 138 then 150
      when tl.voltage_kv >= 115 then 120
      when tl.voltage_kv >= 69  then 50
      else 25
    end as thermal_mw
  from infrastructure_raw.transmission_lines tl
)
select
  r.admin_code as fips,
  count(lt.id) as n_boundary_lines,
  coalesce(sum(lt.thermal_mw), 0) as inbound_thermal_sum,
  coalesce(sum(case when lt.raw_attributes->>'status_raw' = 'NOT AVAILABLE'
                     then lt.thermal_mw else 0 end), 0) as thermal_from_unknown_status
from core.regions r
left join line_thermal lt
  on ST_Intersects(lt.geom, ST_Boundary(r.geometry))
where r.admin_code like '51%%'
group by r.admin_code;
"""

SQL_AXIS1_PLANTS = """
select
  r.admin_code as fips,
  count(pp.id) as n_op_plants,
  coalesce(sum(pp.net_summer_capacity_mw), 0) as net_summer_gen_mw
from core.regions r
left join infrastructure_raw.power_plants pp on pp.region_id = r.id
where r.admin_code like '51%%'
group by r.admin_code;
"""

SQL_PLANTS_FALLBACK_GLOBAL = """
select
  count(*) as total_va_plants,
  count(*) filter (where raw_attributes->>'geo_method' = 'eia_county_fallback_unresolved') as n_fallback
from infrastructure_raw.power_plants
where source = 'EIA860_2024';
"""

SQL_AXIS2_QUEUE = """
select
  r.admin_code as fips,
  coalesce(sum(iq.poi_request_mw), 0) as queue_mw_active
from core.regions r
left join infrastructure_raw.interconnection_queue iq
  on iq.region_id = r.id and iq.status = 'active' and iq.iso = 'PJM'
where r.admin_code like '51%%'
group by r.admin_code;
"""

SQL_AXIS3_DC = """
select
  r.admin_code as fips,
  count(di.id) as n_operating_dc,
  coalesce(sum(0.70 * di.capacity_mw), 0) as operating_dc_load_mw
from core.regions r
left join infrastructure_raw.dc_inventory di
  on di.region_id = r.id and di.status = 'operational' and di.capacity_mw is not null
where r.admin_code like '51%%'
group by r.admin_code;
"""


def fetch_df(conn, sql: str):
    import pandas as pd
    return pd.read_sql(sql, conn)


def compute_peak_adj(va_fips: list[str]) -> "pd.Series":
    """
    Peak_base = годовой почасовой максимум за 2023 (NREL OEDI 8562).
    Залочено: единственный год 2023; max(summer,winter) операционально =
    annual max (SPEC §2.2 RES_return — подтверждено, не гадаем).

    NREL-файл хранится в HDFStore Fixed-формате (подтверждено на практике,
    не в Table-формате) — он НЕ поддерживает партиционный select по columns=
    или where= (TypeError: "cannot pass a column specification when reading
    a Fixed format store"). Поэтому читаем датасет целиком в память
    (~1.6-2 ГБ, размер файла это подтверждает) и фильтруем средствами pandas
    после загрузки, а не средствами HDFStore.
    """
    import pandas as pd

    if not NREL_H5.exists():
        log.error("NREL H5 файл не найден: %s — Peak_adj не может быть вычислен.", NREL_H5)
        raise FileNotFoundError(NREL_H5)

    cols = [f"p{fips}" for fips in va_fips]
    store = pd.HDFStore(str(NREL_H5), mode="r")
    try:
        available = store.select("/data", start=0, stop=0).columns
        missing = [c for c in cols if c not in available]
        if missing:
            log.warning("Колонки НЕ найдены в NREL-файле (Peak_base будет NaN для них): %s", missing)
        cols_present = [c for c in cols if c in available]

        log.info("Пробую частичное чтение (columns+where)...")
        try:
            df_2023 = store.select(
                "/data",
                where="index >= '2023-01-01' and index < '2024-01-01'",
                columns=cols_present,
            )
        except TypeError:
            log.warning(
                "Файл в Fixed-формате — партиционное чтение не поддержано. "
                "Читаю датасет ЦЕЛИКОМ в память (~1.6-2 ГБ, может занять 1-2 минуты)..."
            )
            df_full = store["/data"]
            log.info("  Полная форма (shape): %s", df_full.shape)
            df_2023 = df_full.loc["2023-01-01":"2023-12-31", cols_present]
            del df_full
    finally:
        store.close()

    peak = df_2023.max(axis=0)
    # переименовать обратно из 'p51001' -> '51001'
    peak.index = [c[1:] for c in peak.index]
    return peak


def main() -> None:
    import pandas as pd

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        regions = fetch_df(conn, SQL_REGIONS)
        axis1_lines = fetch_df(conn, SQL_AXIS1_LINES)
        axis1_plants = fetch_df(conn, SQL_AXIS1_PLANTS)
        axis2_queue = fetch_df(conn, SQL_AXIS2_QUEUE)
        axis3_dc = fetch_df(conn, SQL_AXIS3_DC)

        fallback_row = fetch_df(conn, SQL_PLANTS_FALLBACK_GLOBAL).iloc[0]
        total_va_plants = int(fallback_row["total_va_plants"]) or 1
        frac_plants_county_fallback_global = float(fallback_row["n_fallback"]) / total_va_plants
        log.info(
            "Глобальный frac_plants_county_fallback = %.4f (%d/%d) — повторяется на каждой строке CSV.",
            frac_plants_county_fallback_global, fallback_row["n_fallback"], total_va_plants,
        )
    finally:
        conn.close()

    log.info("Регионов VA: %d", len(regions))
    for df_name, df in [("axis1_lines", axis1_lines), ("axis1_plants", axis1_plants),
                         ("axis2_queue", axis2_queue), ("axis3_dc", axis3_dc)]:
        if len(df) != len(regions):
            log.warning("%s вернул %d строк, ожидалось %d (проверь LEFT JOIN).", df_name, len(df), len(regions))

    df = regions.merge(axis1_lines, on="fips", how="left")
    df = df.merge(axis1_plants, on="fips", how="left")
    df = df.merge(axis2_queue, on="fips", how="left")
    df = df.merge(axis3_dc, on="fips", how="left")
    df = df.fillna(0)

    peak_base_series = compute_peak_adj(df["fips"].tolist())
    df["peak_base"] = df["fips"].map(peak_base_series)

    if df["peak_base"].isna().any():
        missing_fips = df.loc[df["peak_base"].isna(), "fips"].tolist()
        log.warning("Peak_base = NaN для %d округов (нет данных в NREL-файле): %s", len(missing_fips), missing_fips)

    # --- Ось 1: Supply deliverability ---------------------------------------
    df["existing_load_adj"] = df["operating_dc_load_mw"]
    df["peak_adj"] = df["peak_base"] + df["existing_load_adj"]

    df["import_proxy_raw"] = df["inbound_thermal_sum"] * PARAMS["transmission_derating_factor"]
    df["import_cap_mw"] = PARAMS["import_cap_pct"] * df["peak_adj"]
    df["import_proxy"] = df[["import_proxy_raw", "import_cap_mw"]].min(axis=1)
    df["import_cap_binding"] = df["import_proxy_raw"] > df["import_cap_mw"]

    df["deliverable"] = (df["net_summer_gen_mw"] + df["import_proxy"] - df["peak_adj"]).clip(lower=0)
    df["adequacy_ratio"] = df["deliverable"] / df["peak_adj"]
    df["deficit_severity"] = (df["net_summer_gen_mw"] + df["import_proxy"] - df["peak_adj"]) / df["peak_adj"]

    df["frac_thermal_status_unknown"] = df.apply(
        lambda r: (r["thermal_from_unknown_status"] / r["inbound_thermal_sum"])
        if r["inbound_thermal_sum"] > 0 else 0.0,
        axis=1,
    )
    df["frac_lines_lookup"] = 1.0  # DLR не используется в этой итерации — 100% линий через voltage_thermal_lookup
    df["frac_plants_county_fallback"] = frac_plants_county_fallback_global

    # --- Ось 2: Interconnection contention -----------------------------------
    completion_rate_pjm = PARAMS["completion_rate_by_iso"]["PJM"]
    df["contention"] = df["queue_mw_active"] * completion_rate_pjm
    df["contention_ratio"] = df["contention"] / df["peak_adj"]

    # --- Ось 3: Compute concentration ----------------------------------------
    df["concentration"] = df["operating_dc_load_mw"] / df["peak_adj"]

    # --- Сборка выходного CSV (SPEC §7) --------------------------------------
    output_cols = [
        "fips", "region_id", "county_name",
        "adequacy_ratio", "deficit_severity", "contention_ratio", "concentration",
        "net_summer_gen_mw", "inbound_thermal_sum", "import_proxy_raw", "import_proxy",
        "peak_base", "existing_load_adj", "peak_adj", "deliverable",
        "queue_mw_active", "contention", "operating_dc_load_mw",
        "import_cap_binding", "frac_lines_lookup", "frac_plants_county_fallback",
        "frac_thermal_status_unknown",
        "n_boundary_lines", "n_op_plants", "n_operating_dc",
    ]
    out = df[output_cols].copy()

    today_str = date.today().strftime("%Y%m%d")
    csv_path = OUTPUT_DIR / f"gci_v2_va_raw_2a_{today_str}.csv"
    out.to_csv(csv_path, index=False)
    log.info("CSV сохранён: %s (%d строк)", csv_path, len(out))

    params_path = OUTPUT_DIR / f"params_used_2a_{today_str}.json"
    with open(params_path, "w", encoding="utf-8") as fh:
        json.dump(PARAMS, fh, indent=2, ensure_ascii=False)
    log.info("Параметры сохранены: %s", params_path)

    # --- Verification: NaN-проверка ------------------------------------------
    nan_check_cols = ["adequacy_ratio", "deficit_severity", "contention_ratio", "concentration"]
    nan_rows = out[out[nan_check_cols].isna().any(axis=1)]
    if not nan_rows.empty:
        log.warning(
            "ВНИМАНИЕ: %d округов с NaN в ключевых метриках (нужно флагировать, не молчать):\n%s",
            len(nan_rows), nan_rows[["fips", "county_name"] + nan_check_cols].to_string(),
        )
    else:
        log.info("NaN-проверка пройдена: нет NaN в adequacy_ratio/deficit_severity/contention_ratio/concentration.")

    # --- Тест вменяемости (диагностика, НЕ override, SPEC §8) ---------------
    log.info("\n" + "=" * 78)
    log.info("Тест вменяемости — NoVA hotspots (ожидаем: deficit_severity<0, высокий concentration):")
    log.info("=" * 78)
    sanity = out[out["fips"].isin(SANITY_CHECK_FIPS.keys())]
    log.info(sanity[["fips", "county_name", "deficit_severity", "concentration", "adequacy_ratio"]].to_string())
    for fips, label in SANITY_CHECK_FIPS.items():
        row = out[out["fips"] == fips]
        if row.empty:
            log.warning("  %s (%s): НЕ НАЙДЕН в выходных данных!", label, fips)
            continue
        ds = row["deficit_severity"].iloc[0]
        if ds >= 0:
            log.warning(
                "  %s (%s): deficit_severity=%.3f >= 0 — ожидался дефицит! "
                "Сигнал для [ARCH]+[RES] переоценить derating/cap в 2b, НЕ патчить движок.",
                label, fips, ds,
            )
        else:
            log.info("  %s (%s): deficit_severity=%.3f — дефицит подтверждён, OK.", label, fips, ds)


if __name__ == "__main__":
    main()
