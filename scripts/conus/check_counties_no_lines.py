r"""
check_counties_no_lines.py -- какие именно 26 округов остались без единой
линии в пределах (intersects). Смотрим площадь округа и минимальное
расстояние до ближайшей линии -- маленький/изолированный округ или
геометрический промах.
"""
import geopandas as gpd
import gci_conus_common as common
from pathlib import Path

HIFLD_SHP = Path(
    r"D:\GISData\Energy\USA\US_Electric_Power_Transmission_Lines_-8378795084787321001"
    r"\Electric_Power_Transmission_Lines_A.shp"
)
ALLOWED_STATUSES = {"IN SERVICE", "NOT AVAILABLE"}

gdf = gpd.read_file(HIFLD_SHP)
gdf = gdf[gdf["STATUS"].isin(ALLOWED_STATUSES)].copy()

counties = common.load_conus_counties()
gdf = gdf.to_crs(counties.crs)

joined = gpd.sjoin(gdf[["geometry"]], counties[["fips", "geometry"]], how="inner", predicate="intersects")
has_line = set(joined["fips"].unique())

no_lines = counties[~counties["fips"].isin(has_line)].copy()
no_lines["area_km2"] = no_lines.geometry.area / 1_000_000
lines_union = gdf.union_all() if hasattr(gdf, "union_all") else gdf.unary_union
no_lines["dist_to_nearest_line_m"] = no_lines.geometry.centroid.distance(lines_union)

print(f"Всего округов без линий: {len(no_lines)}\n")
cols = ["fips", "NAMELSAD", "STATEFP", "area_km2", "dist_to_nearest_line_m"]
print(no_lines[cols].sort_values("area_km2").to_string(index=False))
