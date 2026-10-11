r"""
diag_generation.py -- диагностическая версия, print(flush=True) на каждом шаге
"""
print("1. Скрипт стартовал", flush=True)

from pathlib import Path
print("2. pathlib импортирован", flush=True)

import pandas as pd
print("3. pandas импортирован", flush=True)

import geopandas as gpd
print("4. geopandas импортирован", flush=True)

import gci_conus_common as common
print("5. gci_conus_common импортирован", flush=True)

PLANT_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\2___Plant_Y2024.xlsx")
GENERATOR_XLSX = Path(r"D:\GISData\Energy\USA\eia8602024\3_1_Generator_Y2024.xlsx")

print(f"6. Plant файл существует: {PLANT_XLSX.exists()}", flush=True)
print(f"7. Generator файл существует: {GENERATOR_XLSX.exists()}", flush=True)

print("8. Начинаю читать Plant...", flush=True)
plant_df = pd.read_excel(PLANT_XLSX, sheet_name="Plant", header=1)
print(f"9. Plant прочитан: {len(plant_df)} строк", flush=True)

print("10. Начинаю читать Generator...", flush=True)
gen_df = pd.read_excel(GENERATOR_XLSX, sheet_name="Operable", header=1)
print(f"11. Generator прочитан: {len(gen_df)} строк", flush=True)

print("12. Начинаю load_conus_counties()...", flush=True)
counties = common.load_conus_counties()
print(f"13. Границы округов загружены: {len(counties)}", flush=True)

print("ВСЁ ОТРАБОТАЛО ДО КОНЦА, проблемы нет", flush=True)
