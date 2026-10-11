# Data licenses

The code in this repository is under the MIT license (`LICENSE.txt`). **Data is not.**

AI Buildout Frontier has no single data license. Each published dataset and each layer carries its
own license, taken from its source, in its `meta.json` (`license` and `sources[].license`). The full
list of sources, licenses and attribution texts is on https://aibuildoutfrontier.org/attribution.
Data files in `data/` follow the license stated in their metadata. Compilations made by the project
from several sources are under CC BY 4.0.

## Exception: data derived from OpenStreetMap

`data/conus/layer_substations_osm_20260913.csv` and `data/conus/layer_substations_osm_meta.json` are
derived from OpenStreetMap and are under the Open Database License (ODbL) 1.0, not under MIT or
CC BY. See `data/conus/NOTICE_substations_osm.md`.

## Before 11 October 2026

Until 11 October 2026 this file did not exist and the repository as a whole carried a CC BY 4.0
notice. That grant stays valid for copies taken before that date, except for the two
OpenStreetMap-derived files above, which were always subject to the ODbL.
