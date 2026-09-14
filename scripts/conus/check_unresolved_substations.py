r"""
check_unresolved_substations.py -- характеризуем 2263 нерезолвленных
подстанции: распределение расстояний до ближайшего округа (тот же тест,
что ловил generation-баг) + примеры с координатами, чтобы увидеть, кривые
это OSM-данные или что-то системное.
"""
import json
from pathlib import Path

import pandas as pd
import geopandas as gpd
import gci_conus_common as common

CACHE_DIR = Path(r"C:\Users\PGS\Documents\AI\AI Buildup Frontier project\data\conus\_osm_cache")


def parse_voltage_kv(voltage_tag):
    if not voltage_tag:
        return None
    values = []
    for part in str(voltage_tag).split(";"):
        try:
            v = float(part.strip())
            if v > 0:
                values.append(v)
        except ValueError:
            continue
    return max(values) / 1000.0 if values else None


records = []
for cache_file in CACHE_DIR.glob("substations_*.json"):
    with open(cache_file, "r", encoding="utf-8") as fh:
        elements = json.load(fh)["elements"]
    for el in elements:
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        elif el["type"] == "way":
            c = el.get("center", {})
            lat, lon = c.get("lat"), c.get("lon")
        else:
            continue
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        records.append({
            "osm_type": el["type"], "osm_id": el["id"], "lat": lat, "lon": lon,
            "name": tags.get("name"), "operator": tags.get("operator"),
        })

df = pd.DataFrame(records).drop_duplicates(subset=["osm_type", "osm_id"])
print(f"Всего после дедупликации: {len(df)}")

points = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
counties = common.load_conus_counties()
points = points.to_crs(counties.crs)

joined, n_unresolved = common.resolve_points_to_counties(points, counties, fallback_buffer_m=1000.0)
unresolved_idx = joined[joined["fips"].isna()].index
unresolved = points.loc[unresolved_idx]

union_counties = counties.union_all() if hasattr(counties, "union_all") else counties.unary_union
unresolved = unresolved.copy()
unresolved["dist_m"] = unresolved.geometry.distance(union_counties)

print(f"\nВсего нерезолвленных: {len(unresolved)}")
print("\nРаспределение расстояний до ближайшего округа:")
print(unresolved["dist_m"].describe().to_string())

print("\nГистограмма по бакетам:")
bins = [0, 500, 1000, 2000, 5000, 10000, 50000, 100000, float("inf")]
labels = ["<500м", "500-1000м", "1-2км", "2-5км", "5-10км", "10-50км", "50-100км", ">100км"]
print(pd.cut(unresolved["dist_m"], bins=bins, labels=labels).value_counts().sort_index().to_string())

print("\n20 ближайших к границе (самые вероятные кандидаты на 'это баг, не OSM'):")
closest = unresolved.nsmallest(20, "dist_m")[["name", "operator", "lat", "lon", "dist_m"]]
print(closest.to_string(index=False))

print("\n10 случайных из дальних (>10км -- предположительно просто кривые OSM-координаты):")
far = unresolved[unresolved["dist_m"] > 10000]
if len(far):
    print(far.sample(min(10, len(far)), random_state=42)[["name", "operator", "lat", "lon", "dist_m"]].to_string(index=False))
