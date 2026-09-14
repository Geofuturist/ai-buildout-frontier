r"""
validate_va_and_missouri.py -- ТЗ-1, раздел "Правила", обязательная сверка
перед сдачей:
  1. VA: net_summer_gen_mw, peak_base/peak_demand_mw, queue_mw_active из
     нового CONUS-пайплайна должны совпадать с gci_v2_va_raw_2a_20260630.csv
     (M2a) по абсолютным величинам.
  2. Миссури: округ St. Louis city и St. Louis County должны быть отдельными
     единицами с разумными значениями, не задвоены и не слиты.

Не сравниваю transmission/substations -- методология намеренно и осознанно
изменена по решению RES, у M2a нет эквивалентных величин для сверки.

Запуск (та же папка, что и gci_conus_common.py):
    python validate_va_and_missouri.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OLD_M2A_CSV = Path(r"C:\Users\PGS\Documents\AI\AI Buildup Frontier project\data\gci_v2_va_raw_2a_20260630.csv")
CONUS_DIR = Path(r"C:\Users\PGS\Documents\AI\AI Buildup Frontier project\data\conus")


def find_latest(pattern: str) -> Path | None:
    matches = sorted(CONUS_DIR.glob(pattern))
    return matches[-1] if matches else None


def main() -> None:
    gen_path = find_latest("layer_generation_eia860_*.csv")
    demand_path = find_latest("layer_demand_nrel8562_*.csv")
    queue_path = find_latest("layer_queue_lbnl_*.csv")

    missing = [p for p, path in [("generation", gen_path), ("demand", demand_path), ("queue", queue_path)] if path is None]
    if missing or not OLD_M2A_CSV.exists():
        print(f"Не найдены файлы: {missing}, M2a CSV существует: {OLD_M2A_CSV.exists()}")
        return

    print(f"Сверяю против: {gen_path.name}, {demand_path.name}, {queue_path.name}\n")

    old = pd.read_csv(OLD_M2A_CSV, dtype={"fips": str})
    gen = pd.read_csv(gen_path, dtype={"fips": str})
    demand = pd.read_csv(demand_path, dtype={"fips": str})
    queue = pd.read_csv(queue_path, dtype={"fips": str})

    va_old = old[old["fips"].str.startswith("51")].copy()
    print(f"VA округов в старом M2a CSV: {len(va_old)} (ожидается 133)")

    merged = va_old[["fips", "county_name", "net_summer_gen_mw", "peak_base", "queue_mw_active"]].merge(
        gen[["fips", "net_summer_gen_mw"]].rename(columns={"net_summer_gen_mw": "net_summer_gen_mw_new"}),
        on="fips", how="left",
    ).merge(
        demand[["fips", "peak_demand_mw"]], on="fips", how="left",
    ).merge(
        queue[["fips", "queue_mw_active"]].rename(columns={"queue_mw_active": "queue_mw_active_new"}),
        on="fips", how="left",
    )

    merged["diff_gen"] = (merged["net_summer_gen_mw"] - merged["net_summer_gen_mw_new"]).abs()
    merged["diff_demand"] = (merged["peak_base"] - merged["peak_demand_mw"]).abs()
    merged["diff_queue"] = (merged["queue_mw_active"] - merged["queue_mw_active_new"]).abs()

    print("\n=== 1. VA: сверка с M2a ===")
    for col, label in [("diff_gen", "net_summer_gen_mw"), ("diff_demand", "peak_base/peak_demand_mw"), ("diff_queue", "queue_mw_active")]:
        max_diff = merged[col].max()
        n_mismatch = (merged[col] > 0.01).sum()
        print(f"{label}: макс. расхождение = {max_diff:.4f}, округов с расхождением >0.01: {n_mismatch}/133")

    mismatches = merged[(merged["diff_gen"] > 0.01) | (merged["diff_demand"] > 0.01) | (merged["diff_queue"] > 0.01)]
    if len(mismatches):
        print(f"\nОкруга с расхождением (показаны все {len(mismatches)}):")
        print(mismatches[["fips", "county_name", "diff_gen", "diff_demand", "diff_queue"]].to_string(index=False))
    else:
        print("\nНи одного расхождения >0.01 ни по одной из трёх величин — полное совпадение.")

    print("\n=== 2. Миссури: независимый город St. Louis ===")
    mo_gen = gen[gen["fips"].str.startswith("29")]
    st_louis = mo_gen[mo_gen["NAMELSAD"].str.contains("St. Louis", case=False, na=False)]
    print(st_louis[["fips", "NAME", "NAMELSAD", "net_summer_gen_mw", "n_op_generators"]].to_string(index=False))
    print(f"\nНайдено отдельных единиц 'St. Louis': {len(st_louis)} (ожидается минимум 2 — city и County, разные fips)")


if __name__ == "__main__":
    main()
