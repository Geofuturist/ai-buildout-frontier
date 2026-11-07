# abf-index 0.1.0 · build report

Index version 0.1.0; frame abf-boundaries-v0.2.0; rule: SPEC_INDEX_territory_v0_1 r5.

## Inputs

| Input | Bytes | sha256 (as it lies) | sha256_lf |
|---|---:|---|---|
| abf-dc manifest.json | 16,105 | `35495d1b02121de1826d984852e41ff7f5de1523cb3f537e5473e4c94672c73f` | `da579f885f5c9e7c6d7c58961ab2ecc9db63ab4462257ce6a18162f61b4505f7` |
| atlas_adm1_countries.csv | 5,034 | `3773f79cb5553dfb66088623421b703209b4f4ae576ee9f4e90d28795cc283ba` | `3773f79cb5553dfb66088623421b703209b4f4ae576ee9f4e90d28795cc283ba` |
| county_records.csv | 154,903 | `369186738ffb6c5bba755c8759c394bc733820bbaefdc38db239f860b8dd93d5` | `369186738ffb6c5bba755c8759c394bc733820bbaefdc38db239f860b8dd93d5` |
| dc_atlas_points.csv | 5,621,611 | `0822f5311bbed4ddb5edb5b51f5ee80bedd9180a12ede0740950d0917ee669ff` | `b4d4aabdbed7d76cc13081bcabe1db6426fe9af57b2781bc3e5f40c93bed1df5` |
| dc_epoch_points.csv | 87,263 | `76305ae2fe6b8c4d85aeea7caec0548079449b65d4c798c3bc335f244b7ade0c` | `bd3d0745c80f38441d9603c4cc38c2640625a84295df4cfc25743669607a6749` |
| energy_plants_gem_tzsam_units.csv | 6,303,133 | `5c38f22585b0b1d2630bd0fcaeb5654cb45c309d016c2992da9c25ab41982c40` | `5c38f22585b0b1d2630bd0fcaeb5654cb45c309d016c2992da9c25ab41982c40` |
| energy_plants_gem_units.csv | 51,356,619 | `b57f0d363456ce8ffdfe01e84df456a8051d6a3e834a0048e29994a1d9df13f9` | `b57f0d363456ce8ffdfe01e84df456a8051d6a3e834a0048e29994a1d9df13f9` |
| gem build_hashes.json | 840 | `4a2d76deb5ea718d3e70f93212f1075850dcd1372158f66830097284dbb3d4d2` | `3bcbad0243ba515d81e8c0309dc22d4b2032fd25dd91db45d0cff7c3986d55eb` |
| operator_type_groups.csv | 519 | `b56080b1a351643c24166abb49603434d0f699f0072f48df1d8851b8343065ad` | `b56080b1a351643c24166abb49603434d0f699f0072f48df1d8851b8343065ad` |
| units.csv | 534,673 | `0e9d68763eff9e4f937939c03136fd0d92bff1f47d94bdec4136b8a43a81b98a` | `126b8017034c2c72a181a47f2aa8d454f0dcadd3a856d9d0fc9ed785f3093e4d` |

## Checks

- OK · sha256_lf of dc_atlas_points.csv = manifest.json of abf-dc 0.2.0: file b4d4aabdbed7d76c..., manifest b4d4aabdbed7d76c...; as it lies: 0822f5311bbed4dd...
- OK · sha256_lf of dc_epoch_points.csv = manifest.json of abf-dc 0.2.0: file bd3d0745c80f3844..., manifest bd3d0745c80f3844...; as it lies: 76305ae2fe6b8c4d...
- OK · sha256_lf of county_records.csv is listed in manifest.json of abf-dc 0.2.0: 369186738ffb6c5b...
- OK · sha256_lf of operator_type_groups.csv is listed in manifest.json of abf-dc 0.2.0: b56080b1a351643c...
- OK · sha256_lf of energy_plants_gem_units.csv = files of build_hashes.json (GEM build): file b57f0d363456ce8f..., build_hashes b57f0d363456ce8f...
- OK · sha256_lf of energy_plants_gem_tzsam_units.csv = files of build_hashes.json (GEM build): file 5c38f22585b0b1d2..., build_hashes 5c38f22585b0b1d2...
- OK · records dc_atlas_points: 9,865 (expected 9,865)
- OK · record_id unique in dc_atlas_points: 
- OK · records dc_epoch_points: 94 (expected 94)
- OK · record_id unique in dc_epoch_points: 
- OK · records energy_plants_gem_units: 164,672 (expected 164,672)
- OK · record_id unique in energy_plants_gem_units: 
- OK · records energy_plants_gem_tzsam_units: 18,732 (expected 18,732)
- OK · record_id unique in energy_plants_gem_tzsam_units: 
- OK · record_id unique across the four layers: 
- OK · every Atlas operator_type has a group in operator_type_groups.csv: []
- OK · countries with ADM1 / ADM2 in units.csv: 108 / ['FRA', 'NOR', 'USA']
- OK · location_accuracy of energy_plants_gem_units is exact/approximate: []
- OK · location_accuracy of energy_plants_gem_tzsam_units is exact/approximate: []
- OK · adm0 is a unit ADM0 of the frame for every record: []
- OK · every adm1 lies in the adm0 of its record: 
- OK · every adm2 lies in the adm0 of its record: 
- OK · every adm1_point / adm2_point lies in adm0_other: 
- OK · every adm2 has its parent as adm1: 
- OK · unit_note values are in the SPEC list: []
- OK · unit_basis = field/point/empty: 
- OK · adm1_point rows (Atlas, point in another country): 4 (pre-flight: 4)
- OK · adm0_other rows abf-dc: 4 (pre-flight: 4)
- OK · adm0_other rows abf-energy: 291 (pre-flight: 291)
- OK · adm0_other rows abf-energync: 102 (pre-flight: 102)
- OK · Atlas USA: adm2 = county_records.csv on all matched records: 3914 records with adm2 (expected 3914)
- OK · Atlas USA records: 4038 (expected 4038)
- OK · Atlas in table countries: field (note empty or region_only) / point (note empty) / empty (region_not_matched without a point, no_unit_near with one): 
- OK · region_only only where the record is by the field and the country has ADM2 (adm2 empty): 
- OK · abf-dc: every record is in exactly one country file: 9,959 rows, 9,959 records
- OK · abf-dc: sum of Epoch power_mw equals the source: 14,076.431 MW
- OK · abf-dc: Atlas records by status_raw equal the source: 
- OK · abf-dc: rows per country file match: 
- OK · abf-energy: every record is in exactly one country file: 164,672 rows, 164,672 records
- OK · abf-energy: sum of capacity_mw by type x status_group equals the source: 64 groups
- OK · abf-energy: rows per country file match: 
- OK · abf-energync: every record is in exactly one country file: 18,732 rows, 18,732 records
- OK · abf-energync: sum of capacity_mw by type x status_group equals the source: 3 groups
- OK · abf-energync: rows per country file match: 
- OK · every country CSV is at most 45 MiB (git): []

## Records

| Set | Layer | Records | with point | adm0 by point | adm0 by field | adm0_other | adm1 filled | adm2 filled | approximate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| abf-dc | dc_atlas_points | 9,865 | 6,087 | 0 | 9,865 | 4 | 8,208 | 4,221 | 6,087 |
| abf-dc | dc_epoch_points | 94 | 71 | 71 | 23 | 0 | 70 | 61 | 71 |
| abf-energy | energy_plants_gem_units | 164,672 | 164,672 | 163,814 | 858 | 291 | 147,269 | 22,439 | 73,268 |
| abf-energync | energy_plants_gem_tzsam_units | 18,732 | 18,732 | 18,732 | 0 | 102 | 11,654 | 68 | 426 |

## unit_basis and unit_note

| Set | Layer | field | point | empty | ambiguous_name | connecticut | no_county_field | no_point | no_state | no_unit_near | point_in_other_country | region_not_matched | region_only |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abf-dc | dc_atlas_points | 7,269 | 939 | 1,657 | 70 | 21 | 32 | 582 | 1 | 0 | 4 | 13 | 15 |
| abf-dc | dc_epoch_points | 0 | 70 | 24 | 0 | 0 | 0 | 22 | 0 | 0 | 0 | 0 | 0 |
| abf-energy | energy_plants_gem_units | 0 | 147,269 | 17,403 | 0 | 0 | 0 | 0 | 0 | 668 | 0 | 0 | 0 |
| abf-energync | energy_plants_gem_tzsam_units | 0 | 11,654 | 7,078 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |

unit_note is empty when the frame has no unit level for the country (P2) or when the unit was found.

## Atlas regions by the field (table countries)

| Country | matched (field) | region_only | region not matched: by point | region_not_matched (no point) |
|---|---:|---:|---:|---:|
| AGO (adm1) | 2 | 0 | 0 | 0 |
| ARM (adm1) | 6 | 0 | 0 | 0 |
| AUS (adm1) | 281 | 0 | 0 | 0 |
| BOL (adm1) | 1 | 0 | 0 | 0 |
| BRA (adm1) | 123 | 0 | 0 | 5 |
| CAN (adm1) | 283 | 0 | 0 | 0 |
| CHN (adm1) | 768 | 0 | 1 | 1 |
| CMR (adm1) | 1 | 0 | 0 | 0 |
| CRI (adm1) | 7 | 0 | 0 | 0 |
| DJI (adm1) | 3 | 0 | 0 | 0 |
| FIN (adm1) | 101 | 0 | 4 | 1 |
| FRA (adm1_or_adm2) | 284 | 15 | 0 | 1 |
| GBR (adm1) | 466 | 0 | 1 | 0 |
| GEO (adm1) | 2 | 0 | 0 | 0 |
| GTM (adm1) | 4 | 0 | 0 | 0 |
| HND (adm1) | 2 | 0 | 0 | 0 |
| IND (adm1) | 286 | 0 | 0 | 0 |
| JPN (adm1) | 192 | 0 | 1 | 0 |
| KWT (adm1) | 2 | 0 | 0 | 0 |
| MNG (adm1) | 3 | 0 | 0 | 0 |
| MYS (adm1) | 149 | 0 | 2 | 4 |
| NGA (adm1) | 16 | 0 | 0 | 1 |
| PRY (adm1) | 5 | 0 | 0 | 0 |
| ROU (adm1) | 16 | 0 | 0 | 0 |
| SGP (adm1) | 69 | 0 | 0 | 0 |
| SLV (adm1) | 2 | 0 | 0 | 0 |
| SUR (adm1) | 2 | 0 | 0 | 0 |
| SWE (adm1) | 80 | 0 | 0 | 0 |
| TGO (adm1) | 1 | 0 | 0 | 0 |
| TTO (adm1) | 1 | 0 | 0 | 0 |
| TUR (adm1) | 28 | 0 | 0 | 0 |
| URY (adm1) | 3 | 0 | 0 | 0 |
| ZAF (adm1) | 42 | 0 | 0 | 0 |
| ZWE (adm1) | 1 | 0 | 0 | 0 |

Total: region not matched and the row moved to the point: 9; region_only: 15; region_not_matched without a point: 13.

## Rows with adm1_point (Atlas: adm0 by the field, point in another country)

| record_id | adm0 | adm0_other | adm1_point | adm2_point |
|---|---|---|---|---|
| ATL-5dd4419f9e0a | LUX | DEU | DEU-1-RP |  |
| ATL-9fd05884e9af | GIB | ESP | ESP-1-AN |  |
| ATL-eae102e176a1 | NLD | DEU | DEU-1-NW |  |
| ATL-f9b07f0e3bde | FRA | DEU | DEU-1-RP |  |

## Geometry: computed (USA, NOR) against display

Rows placed by point in USA / NOR whose unit differs between the two geometries:

| Set | rows in USA/NOR by point | adm1 differs | adm2 differs |
|---|---:|---:|---:|
| abf-dc | 99 | 0 | 0 |
| abf-energy | 17,800 | 5 | 19 |
| abf-energync | 22 | 0 | 0 |

## File sizes (country files)

| Set | Files | Rows | CSV MiB | gzip MiB | largest CSV (country, MiB) | largest gzip MiB |
|---|---:|---:|---:|---:|---|---:|
| abf-dc | 126 | 9,959 | 1.5 | 0.3 | USA 0.63 | 0.10 |
| abf-energy | 218 | 164,672 | 26.8 | 2.5 | CHN 6.81 | 0.63 |
| abf-energync | 155 | 18,732 | 3.2 | 0.3 | KOR 0.46 | 0.04 |

Ten largest country files (CSV bytes / gzip bytes):

| Set | Country | Rows | CSV | gzip |
|---|---|---:|---:|---:|
| abf-energy | CHN | 39,928 | 7,139,437 | 656,839 |
| abf-energy | USA | 17,223 | 3,012,123 | 307,082 |
| abf-energy | JPN | 12,082 | 2,223,357 | 134,098 |
| abf-energy | DEU | 12,092 | 2,058,986 | 214,460 |
| abf-energy | BRA | 10,464 | 1,828,066 | 120,881 |
| abf-energy | GRC | 7,236 | 1,248,905 | 108,561 |
| abf-energy | GBR | 5,744 | 963,595 | 104,203 |
| abf-energy | POL | 5,488 | 963,576 | 88,184 |
| abf-energy | IND | 5,812 | 948,917 | 82,389 |
| abf-energy | FRA | 4,649 | 807,291 | 86,378 |

## Output files and SHA-256

| File | sha256 |
|---|---|
| abf-dc/adm0_other.csv | `fa50fdff1f8e9add2d830b2902a8115944a753d9293ffdcea7d1bee5c3dae7e8` |
| abf-dc/index_abf-dc.zip | `5be07f1cf26d75332c4a902f018e4bfcd60297fdca22aa7f12ca232b231368a8` |
| abf-dc/meta.json | `1eddbeb135f2865b5cc63b217c0895805e9801d4259162e150a65621126b9721` |
| abf-dc/summary.csv | `d0b433c2be84c5fb0e2047869b6c89bd0d20ac387d1d5202be389c714d453601` |
| abf-energy/adm0_other.csv | `80c77eca5930e7f6a375a72223d791af1098d3ff4870ea078da94d3be8489980` |
| abf-energy/index_abf-energy.zip | `6dfd97e2d95d0d8d535c2015a8cc28e00eb03e04c9b744ac24efce512145bfd2` |
| abf-energy/meta.json | `4a2931c412c43709fd27a48b7104f118369f8ce993126d41c7dfd216191e409a` |
| abf-energy/summary.csv | `0bd9777b5e8ff267ce8ebd81a4e88a869f5203f7f103866450d816f3b8bf3788` |
| abf-energync/adm0_other.csv | `fdeb48d59835b6c8613d77475b1a64cde73da5636708a8b30cd2ff670e99bf0b` |
| abf-energync/index_abf-energync.zip | `ff2661d842c7263078bfd258a15907bb78f680c42fde552d7d41b42c16efe7a3` |
| abf-energync/meta.json | `26b5e5d47a36503e15b14ad2e515d59b281837f29382ba3db082a0e3fa15fa69` |
| abf-energync/summary.csv | `faff888e6932b0923dcd83f0a216c0ab326476cf66b5463c80487e009211d00b` |

All 1013 output files with SHA-256 are in `build_hashes.json` (country files, `.csv.gz`, summary, meta, zip).

Rerun against the previous `build_hashes.json`: identical.
Build time 6 s.
