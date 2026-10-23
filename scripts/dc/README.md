# scripts/dc — abf-dc v0.1.0 (world data centers: Atlas of Data Center Politics, Epoch AI)

Spec: `SPEC_DC_world_v0_1_0.md` r2 (abf-scratch, `tasks/`). Inputs, outputs and research files are NOT in this repository.

| file | what |
|---|---|
| `dc_http.py` | network helpers: robots.txt (RFC 9309) is read before the first request to a host; pauses; request log |
| `dc_fetch.py` | downloads Census Gazetteer 2023 and the abf-boundaries v0.2.0 files (Zenodo, md5 checked) |
| `dc_lib.py` | text normalisation, address parser, GeoNames / alias / country loaders |
| `dc_atlas.py` | Atlas copies -> records (by header), repeated blocks, `record_id`, groups |
| `dc_place.py` | place chain (section 2.3), `iso3_frame`, contested zones |
| `dc_power.py` | power fields, P9 check |
| `dc_count.py` | `dc_atlas_count_adm0`, `groups.csv` |
| `dc_checks.py` | `checks.csv` (Epoch x `atlas_dcp`), the table for V, stop checks (section 2.9) |
| `dc_build.py` | orchestration; writes the layers, `sources_manifest.json`, `build_log.json`, `build_report.md` |
| `dc_ver_sample.py` | sample frames for [CODE-DC]_ver (SPEC section 3): place layers and check cells |
| `dc_eval_step3.py` | accuracy of step 3 on the scouting reference (no network); `--without-r3c` = records without an address |
| `test_dc_smoke.py` | smoke tests without network or data |

Windows cmd, from the repo root:

    python -m pip install pandas pyarrow shapely geopandas pyproj requests openpyxl
    python scripts\dc\test_dc_smoke.py
    python scripts\dc\dc_fetch.py --sources-dir "D:\GISData\DC\sources"
    python scripts\dc\dc_build.py --inputs-dir "D:\GISData\DC\inputs" --sources-dir "D:\GISData\DC\sources" --out-dir "D:\GISData\DC\out\abf-dc-v0.1.0"

Add `--v-table "D:\GISData\DC\review_atlas_dcp_V_20261023.xlsx" --v-table-date 2026-10-23` once V has filled the table (the date is the date of the verdicts). The re-check log of the independent check is read from `<inputs>\ver_check\ver_recheck_log_DC_v0_1_0.csv` (`--recheck-log`). Compare two builds by `record_hashes.csv`
(the hash of every published field of a record except `checked_at`).
