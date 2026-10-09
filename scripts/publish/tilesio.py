"""Writers for layer files (helper module, not run directly).

Run command: none. This is a helper module, it is imported by build_release.py.

All writers are deterministic: fixed compression, fixed gzip header (mtime=0),
fixed coordinate precision, rows in the order given by the caller.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

from common import gzip_deterministic

log = logging.getLogger("publish.io")

COORD_PRECISION = 6  # decimals, RFC 7946 files and tile inputs
PARQUET_COMPRESSION = "zstd"
PARQUET_LEVEL = 9


def _clean_for_ogr(df: pd.DataFrame) -> pd.DataFrame:
    """Plain numpy/object dtypes so that GDAL gets simple columns (NaN -> null)."""
    out = df.copy()
    for col in out.columns:
        if col == "geometry":
            continue
        dtype = out[col].dtype
        if str(dtype) in ("Int64", "Int32"):
            out[col] = out[col].astype("float64") if out[col].isna().any() else out[col].astype("int64")
        elif str(dtype) == "boolean":
            out[col] = out[col].astype(object).where(out[col].notna(), None)
        elif str(dtype).startswith("string"):
            out[col] = out[col].astype(object).where(out[col].notna(), None)
    return out


def write_parquet(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """GeoParquet 1.0, EPSG:4326, zstd, no index."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(
        path,
        index=False,
        compression=PARQUET_COMPRESSION,
        compression_level=PARQUET_LEVEL,
        schema_version="1.0.0",
    )


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """CSV without geometry: UTF-8 without BOM, LF, empty string for missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", na_rep="")


def write_geojson_gz(gdf: gpd.GeoDataFrame, dst: Path, layer_name: str, tmp_dir: Path) -> None:
    """RFC 7946 GeoJSON with 6 decimals, gzipped with mtime=0."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{layer_name}.geojson"
    if tmp.exists():
        tmp.unlink()
    pyogrio.write_dataframe(
        _clean_for_ogr(gdf),
        tmp,
        driver="GeoJSON",
        layer=layer_name,
        RFC7946="YES",
        COORDINATE_PRECISION=COORD_PRECISION,
        WRITE_NAME="NO",
    )
    gzip_deterministic(tmp, dst)
    tmp.unlink()


def _py(value: Any) -> Any:
    """numpy / pandas scalar -> JSON-safe python value (missing -> None)."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def iter_tile_features(
    gdf: gpd.GeoDataFrame,
    props: list[str],
    minzoom: pd.Series | None = None,
) -> Iterator[str]:
    """One GeoJSON feature per line for Tippecanoe (newline-delimited GeoJSON)."""
    geoms = shapely.set_precision(gdf.geometry.values, 10 ** -COORD_PRECISION)
    geo_json = shapely.to_geojson(geoms)
    columns = [gdf[p].tolist() for p in props]
    mz = minzoom.tolist() if minzoom is not None else None
    for i, geo in enumerate(geo_json):
        feature: dict[str, Any] = {
            "type": "Feature",
            "properties": {p: _py(col[i]) for p, col in zip(props, columns)},
            "geometry": json.loads(geo),
        }
        if mz is not None and mz[i] is not None:
            feature["tippecanoe"] = {"minzoom": int(mz[i])}
        yield json.dumps(feature, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write_geojsonseq_gz(
    gdf: gpd.GeoDataFrame,
    dst: Path,
    props: list[str],
    tmp_dir: Path,
    minzoom: pd.Series | None = None,
) -> int:
    """Write the input of Tippecanoe (not published). Returns the feature count."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / (dst.name + ".tmp")
    count = 0
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for line in iter_tile_features(gdf, props, minzoom):
            fh.write(line)
            fh.write("\n")
            count += 1
    gzip_deterministic(tmp, dst)
    tmp.unlink()
    return count


def read_geo(path: Path, expect_crs: int = 4326) -> gpd.GeoDataFrame:
    """Read a GeoParquet file and make sure it is in EPSG:4326."""
    gdf = gpd.read_parquet(path)
    if gdf.crs is None:
        log.warning("%s has no CRS, EPSG:%d assumed", path.name, expect_crs)
        gdf = gdf.set_crs(expect_crs)
    elif gdf.crs.to_epsg() != expect_crs:
        log.info("%s: reprojecting %s -> EPSG:%d", path.name, gdf.crs.to_string(), expect_crs)
        gdf = gdf.to_crs(expect_crs)
    return gdf


def bbox_of(gdf: gpd.GeoDataFrame) -> list[float]:
    """[west, south, east, north] rounded to 4 decimals."""
    minx, miny, maxx, maxy = (float(v) for v in gdf.total_bounds)
    return [round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4)]
