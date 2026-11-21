# abf-index 0.2.0 · build report

Index version 0.2.0; frame abf-boundaries-v0.3.0; rules: SPEC_INDEX_territory_v0_1 r11 and SPEC_INDEX_territory_v0_2 r3.

## Inputs

| Input | Bytes | sha256 (as it lies) | sha256_lf |
|---|---:|---|---|
| abf-boundaries manifest.json | 16,443 | `396f84bca93852d015d2e8b68886185dfcf4b38ec25146a4603490682e54300e` | `396f84bca93852d015d2e8b68886185dfcf4b38ec25146a4603490682e54300e` |
| abf-dc manifest.json | 16,105 | `35495d1b02121de1826d984852e41ff7f5de1523cb3f537e5473e4c94672c73f` | `da579f885f5c9e7c6d7c58961ab2ecc9db63ab4462257ce6a18162f61b4505f7` |
| atlas_adm1_aliases.csv | 6,285 | `e03b72e53d35feb05bb5794103de5856d06407f3a1f57145182727a27693c79a` | `e03b72e53d35feb05bb5794103de5856d06407f3a1f57145182727a27693c79a` |
| atlas_adm1_countries.csv | 7,749 | `a4c3d8aeccc50dfda94c8b730044ed88a6bf041dfb7b18fdd5312ba4294b36ea` | `bad38ac6bf64793957f570825f41a228b5d8242c6526fdeb77faba7aa69f2a50` |
| county_records.csv | 154,903 | `369186738ffb6c5bba755c8759c394bc733820bbaefdc38db239f860b8dd93d5` | `369186738ffb6c5bba755c8759c394bc733820bbaefdc38db239f860b8dd93d5` |
| dc_atlas_points.csv | 5,621,611 | `0822f5311bbed4ddb5edb5b51f5ee80bedd9180a12ede0740950d0917ee669ff` | `b4d4aabdbed7d76cc13081bcabe1db6426fe9af57b2781bc3e5f40c93bed1df5` |
| dc_epoch_points.csv | 87,263 | `76305ae2fe6b8c4d85aeea7caec0548079449b65d4c798c3bc335f244b7ade0c` | `bd3d0745c80f38441d9603c4cc38c2640625a84295df4cfc25743669607a6749` |
| energy_plants_gem_tzsam_units.csv | 6,303,133 | `5c38f22585b0b1d2630bd0fcaeb5654cb45c309d016c2992da9c25ab41982c40` | `5c38f22585b0b1d2630bd0fcaeb5654cb45c309d016c2992da9c25ab41982c40` |
| energy_plants_gem_units.csv | 51,356,619 | `b57f0d363456ce8ffdfe01e84df456a8051d6a3e834a0048e29994a1d9df13f9` | `b57f0d363456ce8ffdfe01e84df456a8051d6a3e834a0048e29994a1d9df13f9` |
| gem build_hashes.json | 840 | `4a2d76deb5ea718d3e70f93212f1075850dcd1372158f66830097284dbb3d4d2` | `3bcbad0243ba515d81e8c0309dc22d4b2032fd25dd91db45d0cff7c3986d55eb` |
| operator_type_groups.csv | 519 | `b56080b1a351643c24166abb49603434d0f699f0072f48df1d8851b8343065ad` | `b56080b1a351643c24166abb49603434d0f699f0072f48df1d8851b8343065ad` |
| units.csv | 612,913 | `17629e7a7d2e627a58eb36cc845e4edf9f10101c33ed918b30802cbb74724bb9` | `17629e7a7d2e627a58eb36cc845e4edf9f10101c33ed918b30802cbb74724bb9` |

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
- OK · units.csv of the frame: ADM0 / ADM1 / ADM2: {'ADM2': 3602, 'ADM1': 2092, 'ADM0': 242} (expected {'ADM0': 242, 'ADM1': 2092, 'ADM2': 3602})
- OK · units of abf-boundaries 0.2.0 are unchanged in 0.3.0 (iso3, level, name, parent_id): 5,511 old units; changed fields {'iso3': 0, 'level': 0, 'name': 0, 'parent_id': 0}; absent 0
- OK · new units are ADM1 of the 15 countries only: 425 new units, countries ['COL', 'EST', 'HKG', 'IDN', 'IRL', 'KOR', 'LUX', 'LVA', 'MEX', 'NZL', 'PER', 'PHL', 'THA', 'TWN', 'VNM']
- OK · countries with ADM1 / ADM2 in units.csv: 123 / ['FRA', 'NOR', 'USA']
- OK · countries with ADM1 in units.csv: 123 (expected 123)
- OK · manifest.json of the frame is abf-boundaries 0.3.0: abf-boundaries 0.3.0
- OK · sha256 of adm1.parquet = manifest.json of the frame: f5f82db05f4e45e3...
- OK · sha256 of adm2.parquet = manifest.json of the frame: d7313373bdebb526...
- OK · sha256 of analysis_col_adm1.parquet = manifest.json of the frame: c78dce38e0870a99...
- OK · sha256 of analysis_est_adm1.parquet = manifest.json of the frame: 29cdcc0e5be95114...
- OK · sha256 of analysis_hkg_adm1.parquet = manifest.json of the frame: d8902762a211f2ad...
- OK · sha256 of analysis_idn_adm1.parquet = manifest.json of the frame: 1b0b603d4eb490d0...
- OK · sha256 of analysis_irl_adm1.parquet = manifest.json of the frame: e4ba62b87b3ef01e...
- OK · sha256 of analysis_kor_adm1.parquet = manifest.json of the frame: d3fd363cbfdfb43a...
- OK · sha256 of analysis_lux_adm1.parquet = manifest.json of the frame: ae7df68abb8729c4...
- OK · sha256 of analysis_lva_adm1.parquet = manifest.json of the frame: a56cc8ae079fa06d...
- OK · sha256 of analysis_mex_adm1.parquet = manifest.json of the frame: d5784a4e133ab675...
- OK · sha256 of analysis_nor_adm1.parquet = manifest.json of the frame: b2745a056a12ab75...
- OK · sha256 of analysis_nor_adm2.parquet = manifest.json of the frame: f37386250af4e6a0...
- OK · sha256 of analysis_nzl_adm1.parquet = manifest.json of the frame: e240ce8b4608dff0...
- OK · sha256 of analysis_per_adm1.parquet = manifest.json of the frame: 644ac285e2e4bc5e...
- OK · sha256 of analysis_phl_adm1.parquet = manifest.json of the frame: b8f6c8c9a0a15281...
- OK · sha256 of analysis_tha_adm1.parquet = manifest.json of the frame: 6a6e163b3d77fe3f...
- OK · sha256 of analysis_twn_adm1.parquet = manifest.json of the frame: 10f578b30a774908...
- OK · sha256 of analysis_usa_adm1.parquet = manifest.json of the frame: b21843119c619a19...
- OK · sha256 of analysis_usa_adm2.parquet = manifest.json of the frame: aaeb8e02070fa62b...
- OK · sha256 of analysis_vnm_adm1.parquet = manifest.json of the frame: f6985b4ffb6254ac...
- OK · sha256 of units.csv = manifest.json of the frame: 17629e7a7d2e627a...
- OK · countries in the Atlas regions table (without USA): 48 (expected 48); new in 0.2.0: ['COL', 'EST', 'HKG', 'IDN', 'IRL', 'KOR', 'LUX', 'LVA', 'MEX', 'NZL', 'PER', 'PHL', 'THA', 'VNM']
- OK · rows of atlas_adm1_aliases.csv: 59 (expected 59); countries ['BRA', 'EST', 'FIN', 'FRA', 'HKG', 'IDN', 'IRL', 'JPN', 'KOR', 'MEX', 'MYS', 'NGA', 'PER', 'PHL', 'THA', 'VNM']
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
- OK · every row of the table of spellings is used by at least one record: 0 unused: []
- OK · record_id of index 0.1.x = record_id of this build: 193,363 old rows, 193,363 records
- OK · every row of index 0.1.x has boundary_release abf-boundaries-v0.2.0: ['abf-boundaries-v0.2.0']
- OK · outside the 15 countries only records of the table of spellings differ from 0.1.x (nine fields byte for byte otherwise): 0 other record(s) differ: []
- OK · records changed by the table of spellings in the countries of 0.1 (BRA, FIN, FRA, JPN, MYS, NGA): 19 (expected 19); by country {'FIN': 5, 'BRA': 5, 'MYS': 6, 'FRA': 1, 'JPN': 1, 'NGA': 1}
- OK · the 15 countries: adm0 equals 0.1.x: 0 differ
- OK · the 15 countries: adm0_basis equals 0.1.x: 0 differ
- OK · the 15 countries: adm0_other equals 0.1.x: 0 differ
- OK · the 15 countries: adm2 equals 0.1.x: 0 differ
- OK · the 15 countries: adm1_point equals 0.1.x: 0 differ
- OK · the 15 countries: adm2_point equals 0.1.x: 0 differ
- OK · the 15 countries: adm1 was empty in 0.1.x (the frame had no ADM1 there): 0 not empty
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
- OK · list of output files against index 0.1.x (new and missing): new 0, missing 0

## Records

| Set | Layer | Records | with point | adm0 by point | adm0 by field | adm0_other | adm1 filled | adm2 filled | approximate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| abf-dc | dc_atlas_points | 9,865 | 6,087 | 0 | 9,865 | 4 | 9,037 | 4,222 | 6,087 |
| abf-dc | dc_epoch_points | 94 | 71 | 71 | 23 | 0 | 71 | 61 | 71 |
| abf-energy | energy_plants_gem_units | 164,672 | 164,672 | 163,814 | 858 | 291 | 156,170 | 22,439 | 73,268 |
| abf-energync | energy_plants_gem_tzsam_units | 18,732 | 18,732 | 18,732 | 0 | 102 | 16,822 | 68 | 426 |

## unit_basis and unit_note

| Set | Layer | field | point | empty | ambiguous_name | connecticut | no_county_field | no_point | no_state | no_unit_near | point_in_other_country | region_not_matched | region_only |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abf-dc | dc_atlas_points | 8,091 | 946 | 828 | 70 | 21 | 32 | 594 | 1 | 0 | 4 | 8 | 15 |
| abf-dc | dc_epoch_points | 0 | 71 | 23 | 0 | 0 | 0 | 22 | 0 | 0 | 0 | 0 | 0 |
| abf-energy | energy_plants_gem_units | 0 | 156,170 | 8,502 | 0 | 0 | 0 | 0 | 0 | 806 | 0 | 0 | 0 |
| abf-energync | energy_plants_gem_tzsam_units | 0 | 16,822 | 1,910 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 |

unit_note is empty when the frame has no unit level for the country (P2) or when the unit was found.

## Atlas regions by the field (table countries)

| Country | matched (field) | region_only | region not matched: by point | region_not_matched (no point) |
|---|---:|---:|---:|---:|
| AGO (adm1) | 2 | 0 | 0 | 0 |
| ARM (adm1) | 6 | 0 | 0 | 0 |
| AUS (adm1) | 281 | 0 | 0 | 0 |
| BOL (adm1) | 1 | 0 | 0 | 0 |
| BRA (adm1) | 128 | 0 | 0 | 0 |
| CAN (adm1) | 283 | 0 | 0 | 0 |
| CHN (adm1) | 768 | 0 | 1 | 1 |
| CMR (adm1) | 1 | 0 | 0 | 0 |
| COL (adm1) | 34 | 0 | 0 | 0 |
| CRI (adm1) | 7 | 0 | 0 | 0 |
| DJI (adm1) | 3 | 0 | 0 | 0 |
| EST (adm1) | 3 | 0 | 0 | 0 |
| FIN (adm1) | 106 | 0 | 0 | 0 |
| FRA (adm1_or_adm2) | 285 | 15 | 0 | 0 |
| GBR (adm1) | 466 | 0 | 1 | 0 |
| GEO (adm1) | 2 | 0 | 0 | 0 |
| GTM (adm1) | 4 | 0 | 0 | 0 |
| HKG (adm1) | 67 | 0 | 0 | 0 |
| HND (adm1) | 2 | 0 | 0 | 0 |
| IDN (adm1) | 147 | 0 | 0 | 0 |
| IND (adm1) | 286 | 0 | 0 | 0 |
| IRL (adm1) | 63 | 0 | 0 | 0 |
| JPN (adm1) | 193 | 0 | 0 | 0 |
| KOR (adm1) | 171 | 0 | 0 | 0 |
| KWT (adm1) | 2 | 0 | 0 | 0 |
| LUX (adm1) | 17 | 0 | 0 | 0 |
| LVA (adm1) | 10 | 0 | 0 | 0 |
| MEX (adm1) | 51 | 0 | 0 | 0 |
| MNG (adm1) | 3 | 0 | 0 | 0 |
| MYS (adm1) | 155 | 0 | 0 | 0 |
| NGA (adm1) | 17 | 0 | 0 | 0 |
| NZL (adm1) | 34 | 0 | 0 | 0 |
| PER (adm1) | 15 | 0 | 0 | 0 |
| PHL (adm1) | 35 | 0 | 6 | 7 |
| PRY (adm1) | 5 | 0 | 0 | 0 |
| ROU (adm1) | 16 | 0 | 0 | 0 |
| SGP (adm1) | 69 | 0 | 0 | 0 |
| SLV (adm1) | 2 | 0 | 0 | 0 |
| SUR (adm1) | 2 | 0 | 0 | 0 |
| SWE (adm1) | 80 | 0 | 0 | 0 |
| TGO (adm1) | 1 | 0 | 0 | 0 |
| THA (adm1) | 89 | 0 | 0 | 0 |
| TTO (adm1) | 1 | 0 | 0 | 0 |
| TUR (adm1) | 28 | 0 | 0 | 0 |
| URY (adm1) | 3 | 0 | 0 | 0 |
| VNM (adm1) | 67 | 0 | 0 | 0 |
| ZAF (adm1) | 42 | 0 | 0 | 0 |
| ZWE (adm1) | 1 | 0 | 0 | 0 |

Total: region not matched and the row moved to the point: 8; region_only: 15; region_not_matched without a point: 8.

## The 15 countries with new ADM1 (COL, EST, HKG, IDN, IRL, KOR, LUX, LVA, MEX, NZL, PER, PHL, THA, TWN, VNM)

adm1 by the Atlas field (table countries), by the point strictly within a unit, by the nearest unit within 22.2 km, no_unit_near, no_point, region_not_matched.

| Set | Country | records | with point | adm1 filled | by field | by point: within | by point: nearest | no_unit_near | no_point | region_not_matched | points in two units |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abf-dc | COL | 34 | 30 | 34 | 34 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | EST | 3 | 1 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | HKG | 67 | 32 | 67 | 67 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | IDN | 148 | 65 | 148 | 147 | 1 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | IRL | 63 | 50 | 63 | 63 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | KOR | 171 | 114 | 171 | 171 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | LUX | 17 | 9 | 17 | 17 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | LVA | 10 | 8 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | MEX | 51 | 15 | 51 | 51 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | NZL | 34 | 26 | 34 | 34 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | PER | 15 | 11 | 15 | 15 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | PHL | 48 | 16 | 41 | 35 | 6 | 0 | 0 | 0 | 7 | 0 |
| abf-dc | THA | 89 | 69 | 89 | 89 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-dc | TWN | 20 | 8 | 8 | 0 | 8 | 0 | 0 | 12 | 0 | 0 |
| abf-dc | VNM | 67 | 38 | 67 | 67 | 0 | 0 | 0 | 0 | 0 | 0 |
| abf-energy | COL | 958 | 958 | 958 | 0 | 945 | 13 | 0 | 0 | 0 | (see abf-dc) |
| abf-energy | EST | 83 | 83 | 73 | 0 | 49 | 24 | 10 | 0 | 0 | (see abf-dc) |
| abf-energy | HKG | 56 | 56 | 56 | 0 | 54 | 2 | 0 | 0 | 0 | (see abf-dc) |
| abf-energy | IDN | 1,092 | 1,092 | 1,092 | 0 | 1,070 | 22 | 0 | 0 | 0 | (see abf-dc) |
| abf-energy | IRL | 622 | 622 | 599 | 0 | 548 | 51 | 23 | 0 | 0 | (see abf-dc) |
| abf-energy | KOR | 844 | 844 | 808 | 0 | 677 | 131 | 36 | 0 | 0 | (see abf-dc) |
| abf-energy | LUX | 60 | 60 | 60 | 0 | 59 | 1 | 0 | 0 | 0 | (see abf-dc) |
| abf-energy | LVA | 50 | 50 | 48 | 0 | 46 | 2 | 2 | 0 | 0 | (see abf-dc) |
| abf-energy | MEX | 987 | 987 | 987 | 0 | 981 | 6 | 0 | 0 | 0 | (see abf-dc) |
| abf-energy | NZL | 259 | 259 | 253 | 0 | 247 | 6 | 6 | 0 | 0 | (see abf-dc) |
| abf-energy | PER | 290 | 290 | 290 | 0 | 289 | 1 | 0 | 0 | 0 | (see abf-dc) |
| abf-energy | PHL | 1,261 | 1,261 | 1,256 | 0 | 1,138 | 118 | 5 | 0 | 0 | (see abf-dc) |
| abf-energy | THA | 449 | 449 | 449 | 0 | 446 | 3 | 0 | 0 | 0 | (see abf-dc) |
| abf-energy | TWN | 498 | 498 | 473 | 0 | 410 | 63 | 25 | 0 | 0 | (see abf-dc) |
| abf-energy | VNM | 1,530 | 1,530 | 1,499 | 0 | 1,256 | 243 | 31 | 0 | 0 | (see abf-dc) |
| abf-energync | COL | 5 | 5 | 5 | 0 | 5 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | EST | 173 | 173 | 173 | 0 | 173 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | IDN | 69 | 69 | 69 | 0 | 69 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | IRL | 6 | 6 | 6 | 0 | 6 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | KOR | 2,926 | 2,926 | 2,926 | 0 | 2,925 | 1 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | LUX | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | LVA | 82 | 82 | 82 | 0 | 82 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | MEX | 1 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | NZL | 7 | 7 | 7 | 0 | 7 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | PER | 3 | 3 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | PHL | 6 | 6 | 6 | 0 | 6 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | THA | 547 | 547 | 547 | 0 | 547 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | TWN | 325 | 325 | 325 | 0 | 325 | 0 | 0 | 0 | 0 | (see abf-dc) |
| abf-energync | VNM | 1,017 | 1,017 | 1,017 | 0 | 1,017 | 0 | 0 | 0 | 0 | (see abf-dc) |

| Set | records | adm1 filled | by field | by point: within | by point: nearest | no_unit_near | no_point | region_not_matched |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| abf-dc | 837 | 818 | 803 | 15 | 0 | 0 | 12 | 7 |
| abf-energy | 9,039 | 8,901 | 0 | 8,215 | 686 | 138 | 0 | 0 |
| abf-energync | 5,168 | 5,168 | 0 | 5,166 | 2 | 0 | 0 | 0 |

Points in two units of one country (lowest unit_id taken), the 15 countries, counted once per distinct point over all sets (lookups of the set records): {}.

## Table of spellings (atlas_adm1_aliases.csv)

59 rows; records placed through it: 379.

| iso3 | adm1_raw | unit_id | records | reason | decided_by |
|---|---|---|---:|---|---|
| BRA | Distrito Federal | BRA-1-DF | 5 | spelling: Portuguese name of the Federal District | human:V |
| EST | Harju | EST-1-0037 | 3 | spelling: short form of Harjumaa | human:V |
| FIN | Finland Proper | FIN-1-19 | 1 | spelling: other English name of Varsinais-Suomi (Southwest Finland) | human:V |
| FIN | Päijät-Häme | FIN-1-16 | 4 | spelling: Finnish name of Päijänne Tavastia | human:V |
| FRA | Haute-Rhin | FRA-2-68 | 1 | spelling: misspelling of Haut-Rhin | human:V |
| HKG | Central and Western | HKG-1-A | 1 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Eastern | HKG-1-C | 3 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Islands | HKG-1-T | 1 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Kowloon City | HKG-1-G | 2 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Kwai Tsing | HKG-1-S | 5 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Kwun Tong | HKG-1-J | 2 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | North | HKG-1-N | 5 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Sai Kung | HKG-1-Q | 16 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Sha Tin | HKG-1-R | 8 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Southern | HKG-1-D | 3 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Tai Po | HKG-1-P | 1 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Tsuen Wan | HKG-1-K | 17 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Wan Chai | HKG-1-B | 1 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| HKG | Wong Tai Sin | HKG-1-H | 2 | spelling: district name without the word District | generated: HKG district-name rule; reviewed: agent:RES7 |
| IDN | Jakarta Raya | IDN-1-31 | 37 | spelling: short form of Daerah Khusus Ibukota Jakarta Raya (DKI Jakarta) | human:V |
| IDN | Jawa Barat | IDN-1-32 | 45 | spelling: Indonesian name of West Java | human:V |
| IDN | Jawa Tengah | IDN-1-33 | 4 | spelling: Indonesian name of Central Java | human:V |
| IDN | Jawa Timur | IDN-1-35 | 8 | spelling: Indonesian name of East Java | human:V |
| IDN | Kalimantan Barat | IDN-1-61 | 1 | spelling: Indonesian name of the province (name in the BIG file) | generated: IDN source_name rule; reviewed: agent:RES7 |
| IDN | Kalimantan Selatan | IDN-1-63 | 1 | spelling: Indonesian name of the province (name in the BIG file) | generated: IDN source_name rule; reviewed: agent:RES7 |
| IDN | Kalimantan Timur | IDN-1-64 | 3 | spelling: Indonesian name of East Kalimantan | human:V |
| IDN | Kepulauan Riau | IDN-1-21 | 18 | spelling: Indonesian name of Riau Islands (not Riau, IDN-1-14) | human:V |
| IDN | Sulawesi Selatan | IDN-1-73 | 2 | spelling: Indonesian name of the province (name in the BIG file) | generated: IDN source_name rule; reviewed: agent:RES7 |
| IDN | Sulawesi Utara | IDN-1-71 | 1 | spelling: Indonesian name of the province (name in the BIG file) | generated: IDN source_name rule; reviewed: agent:RES7 |
| IDN | Sumatera Selatan | IDN-1-16 | 2 | spelling: Indonesian name of the province (name in the BIG file) | generated: IDN source_name rule; reviewed: agent:RES7 |
| IDN | Sumatera Utara | IDN-1-12 | 2 | spelling: Indonesian name of the province (name in the BIG file) | generated: IDN source_name rule; reviewed: agent:RES7 |
| IRL | Fingal | IRL-1-D | 14 | within: a local authority area wholly inside County Dublin | human:V |
| IRL | Laoighis | IRL-1-LS | 1 | spelling: older spelling of Laois | human:V |
| IRL | South Dublin | IRL-1-D | 26 | within: a local authority area wholly inside County Dublin | human:V |
| JPN | Miyagi Prefecture | JPN-1-04 | 1 | spelling: name with the word Prefecture | human:V |
| KOR | Gwangju | KOR-1-X2436 | 5 | merged: Gwangju Metropolitan City is wholly part of Jeonnam-Gwangju Integrated Special City under Act No. 21446, Art. 7 [apply only if points confirm: Gyeonggi also has a city named Gwangju] | human:V |
| KOR | South Jeolla | KOR-1-X2436 | 5 | merged: South Jeolla Province is wholly part of Jeonnam-Gwangju Integrated Special City under Act No. 21446, Art. 7 | human:V |
| MEX | Distrito Federal | MEX-1-09 | 2 | former name: name of Mexico City before 2016 | human:V |
| MEX | México | MEX-1-15 | 10 | spelling: official name of the State of Mexico (INEGI) | generated: MEX state-name rule; reviewed: agent:RES7 |
| MYS | Melaka | MYS-1-04 | 3 | spelling: Malay name of Malacca | human:V |
| MYS | Pulau Pinang | MYS-1-07 | 3 | spelling: Malay name of Penang | human:V |
| NGA | Ogun State | NGA-1-OG | 1 | spelling: name with the word State | human:V |
| PER | Lima Province | PER-1-15 | 13 | within: the province of Lima (Metropolitan Lima) lies wholly in the department of Lima, which this unit covers | human:V |
| PHL | Angeles | PHL-1-03 | 2 | within: Angeles City, in Pampanga, Central Luzon (Region III) | human:V |
| PHL | Batangas | PHL-1-04 | 2 | within: a province of Calabarzon (Region IV-A) | human:V |
| PHL | Caloocan | PHL-1-13 | 1 | within: a city of Metro Manila (National Capital Region) | human:V |
| PHL | Camarines Norte | PHL-1-05 | 1 | within: a province of Bicol (Region V) | human:V |
| PHL | Laguna | PHL-1-04 | 6 | within: a province of Calabarzon (Region IV-A) | human:V |
| PHL | Makati | PHL-1-13 | 5 | within: a city of Metro Manila (National Capital Region) | human:V |
| PHL | Mandaue | PHL-1-07 | 2 | within: Mandaue City, in Cebu, Central Visayas (Region VII) | human:V |
| PHL | Manila | PHL-1-13 | 2 | within: a city of Metro Manila (National Capital Region) | human:V |
| PHL | Pampanga | PHL-1-03 | 2 | within: a province of Central Luzon (Region III) | human:V |
| PHL | Paranaque | PHL-1-13 | 2 | within: a city of Metro Manila (National Capital Region) | human:V |
| PHL | Pasig | PHL-1-13 | 2 | within: a city of Metro Manila (National Capital Region) | human:V |
| PHL | Quezon City | PHL-1-13 | 5 | within: a city of Metro Manila (National Capital Region) | human:V |
| THA | Bangkok Metropolis | THA-1-10 | 25 | spelling: official English name of Bangkok | human:V |
| VNM | Bình Dương | VNM-1-79 | 4 | merged: Binh Duong province is wholly part of Ho Chi Minh City under Resolution No. 202/2025/QH15, Art. 1(16) [not code-checked] | human:V |
| VNM | Ha Noi | VNM-1-01 | 22 | spelling: Vietnamese form of Hanoi | human:V |
| VNM | Đà Nẵng | VNM-1-48 | 7 | spelling: Vietnamese spelling of Da Nang | human:V |

## Regression against index 0.1.x

Records compared: 193,363. Nine fields (adm0, adm0_basis, adm0_other, adm1, adm2, unit_basis, unit_note, adm1_point, adm2_point):

- outside the 15 countries: 19 records differ, all through the table of spellings (expected 19): BRA, FIN, FRA, JPN, MYS, NGA;
- the 15 countries (15,044 records): adm0, adm0_basis, adm0_other, adm2, adm1_point, adm2_point equal 0.1.x; adm1 filled 14,887 (empty in 0.1.x);
- unit_note transitions in the 15 (old -> new): {"'' -> ''": 14886, "'' -> 'no_unit_near'": 138, "'' -> 'no_point'": 12, "'' -> 'region_not_matched'": 7, "'point_in_other_country' -> 'point_in_other_country'": 1};
- unit_basis transitions in the 15 (old -> new): {"'' -> 'point'": 14084, "'' -> 'field'": 803, "'' -> ''": 157}.

`boundary_release` changes from abf-boundaries-v0.2.0 to abf-boundaries-v0.3.0 in all rows.

Records of the countries of 0.1 changed by the table of spellings (list):

| record_id | adm0 | 0.1.x | 0.2.0 |
|---|---|---|---|
| ATL-127740fc9118 | FIN | adm1=- adm2=- basis=- note=region_not_matched | adm1=FIN-1-16 adm2=- basis=field note=- |
| ATL-158a1e168274 | FIN | adm1=FIN-1-16 adm2=- basis=point note=- | adm1=FIN-1-16 adm2=- basis=field note=- |
| ATL-193c59d79675 | BRA | adm1=- adm2=- basis=- note=region_not_matched | adm1=BRA-1-DF adm2=- basis=field note=- |
| ATL-20925a36faef | BRA | adm1=- adm2=- basis=- note=region_not_matched | adm1=BRA-1-DF adm2=- basis=field note=- |
| ATL-274f5e7dc190 | MYS | adm1=MYS-1-04 adm2=- basis=point note=- | adm1=MYS-1-04 adm2=- basis=field note=- |
| ATL-2a847c743134 | MYS | adm1=- adm2=- basis=- note=region_not_matched | adm1=MYS-1-04 adm2=- basis=field note=- |
| ATL-36026a9c1798 | FRA | adm1=- adm2=- basis=- note=region_not_matched | adm1=FRA-1-44 adm2=FRA-2-68 basis=field note=- |
| ATL-3db3dd8e976a | MYS | adm1=MYS-1-04 adm2=- basis=point note=- | adm1=MYS-1-04 adm2=- basis=field note=- |
| ATL-3dda9d8996c0 | BRA | adm1=- adm2=- basis=- note=region_not_matched | adm1=BRA-1-DF adm2=- basis=field note=- |
| ATL-52e2092f03d0 | BRA | adm1=- adm2=- basis=- note=region_not_matched | adm1=BRA-1-DF adm2=- basis=field note=- |
| ATL-5b0bbe95820a | FIN | adm1=FIN-1-16 adm2=- basis=point note=- | adm1=FIN-1-16 adm2=- basis=field note=- |
| ATL-a2cee9fe2f9e | JPN | adm1=JPN-1-04 adm2=- basis=point note=- | adm1=JPN-1-04 adm2=- basis=field note=- |
| ATL-ae36374acf2b | FIN | adm1=FIN-1-19 adm2=- basis=point note=- | adm1=FIN-1-19 adm2=- basis=field note=- |
| ATL-becd9db135e3 | MYS | adm1=- adm2=- basis=- note=region_not_matched | adm1=MYS-1-07 adm2=- basis=field note=- |
| ATL-ca8126f98e07 | FIN | adm1=FIN-1-16 adm2=- basis=point note=- | adm1=FIN-1-16 adm2=- basis=field note=- |
| ATL-ddfd9668234e | MYS | adm1=- adm2=- basis=- note=region_not_matched | adm1=MYS-1-07 adm2=- basis=field note=- |
| ATL-ed577d09964c | MYS | adm1=- adm2=- basis=- note=region_not_matched | adm1=MYS-1-07 adm2=- basis=field note=- |
| ATL-f2b4dc29e50b | NGA | adm1=- adm2=- basis=- note=region_not_matched | adm1=NGA-1-OG adm2=- basis=field note=- |
| ATL-fc09ba1232e7 | BRA | adm1=- adm2=- basis=- note=region_not_matched | adm1=BRA-1-DF adm2=- basis=field note=- |

Output files against index 0.1.x: new 0 []; missing 0 [].

## Frame files read (sha256)

| File | sha256 |
|---|---|
| adm1.parquet | `f5f82db05f4e45e37fb049ac58905c9ae8dc8794543fef8b202e866fa562ac35` |
| adm2.parquet | `d7313373bdebb5265dde70c4ea17b14f484b7deb8b2b306d98c6098f6693cf52` |
| analysis_col_adm1.parquet | `c78dce38e0870a9924ca25709449aff178376a22ab33c958f776a9861957f557` |
| analysis_est_adm1.parquet | `29cdcc0e5be951140a13a034bb4f6761d764f7bb528dab0e1a6d8ccc6d78cff0` |
| analysis_hkg_adm1.parquet | `d8902762a211f2ad9d3d0009a39a23f098101f510011e0a4a07754c93ef4248a` |
| analysis_idn_adm1.parquet | `1b0b603d4eb490d015ff6f3195544b223b7ce968d3d784e8367687ed8ec85744` |
| analysis_irl_adm1.parquet | `e4ba62b87b3ef01e18874415088310055c4ed78b6dd627f45313d153731ccbca` |
| analysis_kor_adm1.parquet | `d3fd363cbfdfb43ac0755794cb689dc08770aaf9a0ee84b4a4126cabc9a0961d` |
| analysis_lux_adm1.parquet | `ae7df68abb8729c46d516026e6d68eb848b468ece70e91324d2891aad572b72e` |
| analysis_lva_adm1.parquet | `a56cc8ae079fa06d8b295ffba8d7f3bc4d0e9546ae5f53dd60d1d3346bcf066f` |
| analysis_mex_adm1.parquet | `d5784a4e133ab67582e42e6f248a0c84b29eee48182251b9bc4ded6fa097563f` |
| analysis_nor_adm1.parquet | `b2745a056a12ab75c4f03f66b3bdf3738d9b88569fe4900dbc9ebe656638f1c9` |
| analysis_nor_adm2.parquet | `f37386250af4e6a0282c2beb465743d768b95afa7dfa6128b960d7266bdaf88b` |
| analysis_nzl_adm1.parquet | `e240ce8b4608dff00c98f3b257261655f9424e7955cf6bf5d3a6ef140c6fbd1b` |
| analysis_per_adm1.parquet | `644ac285e2e4bc5e08d6cdbe2a58845fea95a1013e9bb1dd5052ab57999435a5` |
| analysis_phl_adm1.parquet | `b8f6c8c9a0a15281239e9d55de4f913028b2f11f164577ee1c5e65973f5af636` |
| analysis_tha_adm1.parquet | `6a6e163b3d77fe3f07c92f3c9c48ebf7cc64bb5df21c34a133600bf4c84d17f6` |
| analysis_twn_adm1.parquet | `10f578b30a774908ebb93e30f16fbbf5d652f7925ce92c4d8762bb34b60212ba` |
| analysis_usa_adm1.parquet | `b21843119c619a1980f0b1cf8f53ec6f726cc4f706c7d00bfc0a538ea05861b5` |
| analysis_usa_adm2.parquet | `aaeb8e02070fa62ba8a946de98173e19108ab6b0200dad496f019c8604d2dac8` |
| analysis_vnm_adm1.parquet | `f6985b4ffb6254ac47784b579a2eb9eef98fbe42f83d2300e175e53c0a2755a3` |
| units.csv | `17629e7a7d2e627a58eb36cc845e4edf9f10101c33ed918b30802cbb74724bb9` |

## Rows with adm1_point (Atlas: adm0 by the field, point in another country)

| record_id | adm0 | adm0_other | adm1_point | adm2_point |
|---|---|---|---|---|
| ATL-5dd4419f9e0a | LUX | DEU | DEU-1-RP |  |
| ATL-9fd05884e9af | GIB | ESP | ESP-1-AN |  |
| ATL-eae102e176a1 | NLD | DEU | DEU-1-NW |  |
| ATL-f9b07f0e3bde | FRA | DEU | DEU-1-RP |  |

## Geometry: computed against display

Rows placed by point whose unit differs between the computed and the display geometry:

| Group | Set | rows by point | adm1 differs | adm2 differs |
|---|---|---:|---:|---:|
| USA, NOR | abf-dc | 99 | 0 | 0 |
| USA, NOR | abf-energy | 17,800 | 5 | 19 |
| USA, NOR | abf-energync | 22 | 0 | 0 |
| the 15 national countries | abf-dc | 15 | 0 | 0 |
| the 15 national countries | abf-energy | 8,901 | 0 | 0 |
| the 15 national countries | abf-energync | 5,168 | 1 | 0 |

## File sizes (country files)

| Set | Files | Rows | CSV MiB | gzip MiB | largest CSV (country, MiB) | largest gzip MiB |
|---|---:|---:|---:|---:|---|---:|
| abf-dc | 126 | 9,959 | 1.5 | 0.3 | USA 0.63 | 0.10 |
| abf-energy | 218 | 164,672 | 27.0 | 2.5 | CHN 6.81 | 0.63 |
| abf-energync | 155 | 18,732 | 3.2 | 0.3 | KOR 0.50 | 0.04 |

Ten largest country files (CSV bytes / gzip bytes):

| Set | Country | Rows | CSV | gzip |
|---|---|---:|---:|---:|
| abf-energy | CHN | 39,928 | 7,139,437 | 656,839 |
| abf-energy | USA | 17,223 | 3,012,123 | 307,084 |
| abf-energy | JPN | 12,082 | 2,223,357 | 134,098 |
| abf-energy | DEU | 12,092 | 2,058,986 | 214,462 |
| abf-energy | BRA | 10,464 | 1,828,066 | 120,881 |
| abf-energy | GRC | 7,236 | 1,248,905 | 108,561 |
| abf-energy | GBR | 5,744 | 963,595 | 104,203 |
| abf-energy | POL | 5,488 | 963,576 | 88,184 |
| abf-energy | IND | 5,812 | 948,917 | 82,389 |
| abf-energy | FRA | 4,649 | 807,291 | 86,378 |

## Output files and SHA-256

| File | sha256 |
|---|---|
| abf-dc/adm0_other.csv | `29e4bd5cbc76997898d6831eb4413443f6dd0576efdb6f85cb2978ef6128f3b1` |
| abf-dc/index_abf-dc.zip | `715834d31696f8cce4ec3325f2737c75343d627851d54b9020a6692c58f51dd7` |
| abf-dc/meta.json | `287ced649ea0b435e009b01e012782ca40d3b7b28b58cabcf87e3fc8bf7f0270` |
| abf-dc/summary.csv | `9833797d8983b4460a5bb89f9baee6b4bef0127b27b9a8561221b4b5b12e4746` |
| abf-energy/adm0_other.csv | `0f3771d8aea779f5974cf961d733c526e2f7713a43cf60119b8dfade30992580` |
| abf-energy/index_abf-energy.zip | `adb7767220818b1bf24089518165ea058a1f1d76749ea048d8a90f235ebb4748` |
| abf-energy/meta.json | `eec879c764d74d42b23ba5dfc93b192a71ad72166b68b74be81ebe1847e2cddc` |
| abf-energy/summary.csv | `17951fc7709e07ab80444613d65a688abf49718a2aeb8312df9fd0561a7cde38` |
| abf-energync/adm0_other.csv | `cd3a448e7c5a5675210dcc0ab39980656f5c6d76b12bb55f1630a03e64806d20` |
| abf-energync/index_abf-energync.zip | `d009aad7b1239741f4164d1126fa366334c9230fec1d125818623a09d63935ed` |
| abf-energync/meta.json | `32805dbd8e072974217087ca3b8f11ea15cac05ac18cd1efc97d4fcf5ec60d1d` |
| abf-energync/summary.csv | `818013d6e3c6e7c1e5f0484b7362d354bd2db8d9ebff9cdaf020cc8b568c3f04` |

All 1013 output files with SHA-256 are in `build_hashes.json` (country files, `.csv.gz`, summary, meta, zip).

Rerun against the previous `build_hashes.json`: identical.
Build time 14 s.
