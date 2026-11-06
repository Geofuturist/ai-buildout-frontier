# build_report · GEM plants · abf-energy / abf-energync 0.1.0

Built: 2026-11-01 11:11:39 (local) · took 84 s · SPEC_GEM_plants_v0_1_0 r4

- Input: `D:\GISData\Energy\GEM\Global Integrated Power September 2026 V2.xlsx` · SHA-256 `34749042643b15cac4423ae67864ad36c391013aa2d5acc65ae7492c5e33ee27`
- Frame: `D:\GISData\Boundaries\out\abf-boundaries-v0.2.0\display` · adm0.parquet `e84e1d13ce5a6ea3…` · contested_areas.parquet `3b0965d9e0f3ec90…`
- Country sheet name column (exact): `GEM Standard Country Name/Area`
- Rerun: **identical** to the previous run (all SHA-256 equal)

## Checks (section 2.7)

| check | result | detail |
|---|---|---|
| rows in the sheet | OK | 183,404 (expected 183,404) |
| TransitionZero records | OK | 18,732 (expected 18,732); rule (?<![A-Za-z])TZ\s*: |
| non-TZ records | OK | 164,672 (expected 164,672) |
| blocks in both sets | OK | 164,672 + 18,732 = 183,404 |
| capacity, both sets | OK | 22,641,663.6 MW (expected 22,641,664) |
| capacity, TZ set | OK | 84,303.8 MW (expected 84,304) |
| abf-energy: record_id unique | OK | 138,504 places |
| abf-energy: sum of n_units | OK | 164,672 = 164,672 blocks |
| abf-energy: MW by type x status_group, places = blocks | OK | 64 cells |
| abf-energync: record_id unique | OK | 18,732 places |
| abf-energync: sum of n_units | OK | 18,732 = 18,732 blocks |
| abf-energync: MW by type x status_group, places = blocks | OK | 3 cells |
| captive_dc | OK | 399 blocks, 227,212.6 MW (expected 399 / 227,213) |
| dc_ppa | OK | 32 blocks, 11,403.5 MW (expected 32 / 11,404) |
| both flags on one block | OK | 0 blocks (September: 0) |
| approximate points | OK | 73,694 (expected 73,694) |
| iso3_gem / iso3_source filled | OK | every row |

## Files

| file | bytes | SHA-256 |
|---|---:|---|
| energy_plants_gem_locations.csv | 38,842,498 (38.8 MB; 37.0 MiB) | `1c7c2e7e8946e9192f0ce580880e6f6caba1cf74ecced2165b4be24732e5708a` |
| energy_plants_gem_tzsam_locations.csv | 5,253,429 (5.3 MB; 5.0 MiB) | `4ff4ff821925f973274632dabc40fd88f97ccccac83443b0f1693bee2d2d754e` |
| energy_plants_gem_tzsam_units.csv | 6,303,133 (6.3 MB; 6.0 MiB) | `5c38f22585b0b1d2630bd0fcaeb5654cb45c309d016c2992da9c25ab41982c40` |
| energy_plants_gem_units.csv | 51,356,619 (51.4 MB; 49.0 MiB) | `b57f0d363456ce8ffdfe01e84df456a8051d6a3e834a0048e29994a1d9df13f9` |
| gem_country_table.csv | 3,808 (0.0 MB; 0.0 MiB) | `66f204d04cae0a8966365d2e8e27d2885c34b579cc73a8d0a21d767d33910abd` |
| gem_iso3_to_adm0.csv | 316 (0.0 MB; 0.0 MiB) | `73cacdfadebebd3c94edb332d75dee3cd827162c7de051716e55345b62af214d` |
| gem_status_groups.csv | 371 (0.0 MB; 0.0 MiB) | `1403c78c9b5e9e64a77f2684d72a637d957f1aef7ce51db625836f3b14755dec` |

Files over 50 MB decimal, which is 47.7 MiB (tell V before commit; the SPEC says 50 MB, GitHub counts MiB): energy_plants_gem_units.csv

## Counts

| set | blocks | locations | places | locations split by point groups | places with n_units_other_set > 0 | their locations |
|---|---:|---:|---:|---:|---:|---:|
| abf-energy | 164,672 | 126,886 | 138,504 | 3,364 | 29 | 15 |
| abf-energync | 18,732 | 18,725 | 18,732 | 4 | 17 | 15 |

Places by status_group x capacity_class:

`abf-energy`

```
capacity_class    100_999  10_99  ge1000   lt10
status_group                                   
announced            2861   2318    1044    244
cancelled            2607   3472    1251    339
construction         2516   1991     532    374
mothballed            215    123      31     11
operating           12875  31001    2035  47804
pre_construction     6119   9961     840   2096
retired              1146    666     198     90
shelved              1223   1956     248    317
```

`abf-energync`

```
capacity_class    10_99   lt10
status_group                  
cancelled             1      0
operating          2088  16642
pre_construction      0      1
```

## MW by type x status_group (blocks)

`abf-energy`

```
status_group         announced  cancelled  construction  mothballed  operating  pre_construction  retired  shelved    TOTAL
type                                                                                                                       
bioenergy                 4274       6129          6059        1301     119988              6327     2427     5807   152314
coal                    298225    1817068        260300       45028    2226469            204519   536549   105665  5493824
geothermal                6013       2593          2063          86      16627              6455      431     3670    37939
hydropower              470279     112663        325861       11140    1278940            319524     2191   129117  2649715
nuclear                 213450     561564         90886       19856     407801             92133   115932    31939  1533561
oil/gas                 350166     370355        263036       58537    2267335            524737    78990   157342  4070497
utility-scale solar     785275     206946        469311         807    1183514           1143623      561   216463  4006500
wind                   1038041     507708        314409        3507    1133954           1300650    18769   295973  4613011
```

`abf-energync`

```
status_group         cancelled  operating  pre_construction  TOTAL
type                                                              
utility-scale solar         15      84285                 4  84304
```

## Country

- iso3_frame_rule: {'within': 177764, 'nearest_12nmi': 4782, '(empty)': 858}
- ADM0 overlaps resolved by iso3_gem: 0 points; points in zones with different controlled_by: 0
- rows with iso3_source != iso3_frame: 1,251, of them iso3_frame empty (farther than 22.2 km from land): 858; both filled but different: 393 (full list: `research\gem\iso3_source_vs_frame.csv`)

Both filled, different:

| iso3_source | iso3_frame | rule | rows |
|---|---|---|---:|
| JOR | PSE | within | 50 |
| CHN | MNG | within | 31 |
| UKR | RUS | within | 31 |
| SGP | MYS | nearest_12nmi | 15 |
| CYP | GBR | within | 13 |
| DEU | CHE | within | 12 |
| MDA | UKR | within | 12 |
| ISR | JOR | within | 9 |
| NLD | DEU | within | 9 |
| SYR | ISR | within | 8 |
| PRT | ESP | within | 8 |
| CZE | POL | within | 7 |
| DEU | POL | within | 7 |
| USA | CAN | within | 7 |
| DEU | AUT | within | 6 |
| DEU | DNK | within | 6 |
| AUT | HUN | within | 5 |
| CHN | MAC | within | 5 |
| FRA | DEU | within | 5 |
| CAN | USA | within | 5 |
| USA | MEX | within | 5 |
| ROU | SRB | within | 4 |
| SRB | XKX | within | 4 |
| COD | RWA | within | 4 |
| BEL | NLD | within | 3 |
| CZE | DEU | within | 3 |
| ITA | SVN | within | 3 |
| PSE | ISR | within | 3 |
| CHE | ITA | within | 3 |
| UKR | RUS | nearest_12nmi | 3 |
| ARG | PRY | within | 3 |
| AZE | IRN | within | 3 |
| BGD | IND | within | 2 |
| COL | VEN | within | 2 |
| EST | RUS | within | 2 |
| GRC | MKD | within | 2 |
| IND | BGD | within | 2 |
| IND | CHN | within | 2 |
| ISR | PSE | within | 2 |
| JOR | ISR | within | 2 |

iso3_frame empty, by iso3_source (top 25):

| iso3_source | rows |
|---|---:|
| CHN | 112 |
| GBR | 86 |
| BRA | 64 |
| KOR | 57 |
| SWE | 50 |
| USA | 49 |
| DEU | 44 |
| NLD | 39 |
| ITA | 39 |
| VNM | 38 |
| AUS | 36 |
| TWN | 32 |
| NOR | 26 |
| IRL | 25 |
| POL | 24 |
| ESP | 21 |
| JPN | 14 |
| BEL | 14 |
| DNK | 13 |
| EST | 10 |
| FRA | 10 |
| ALA | 7 |
| PHL | 6 |
| NZL | 6 |
| ARE | 5 |

Rows inside a contested_areas zone (control_iso3 filled): 31

| iso3_source | control_iso3 | rows |
|---|---|---:|
| UKR | RUS | 31 |

- rows of `gem_iso3_to_adm0.csv`: 6 (accepted by the script: 6, manual from RES: 0)
  - BES -> NLD · part of NLD in the abf-boundaries frame
  - GLP -> FRA · part of FRA in the abf-boundaries frame
  - GUF -> FRA · part of FRA in the abf-boundaries frame
  - MTQ -> FRA · part of FRA in the abf-boundaries frame
  - MYT -> FRA · part of FRA in the abf-boundaries frame
  - REU -> FRA · part of FRA in the abf-boundaries frame

## For [RES]7

- locations whose blocks (all types and statuses together) spread more than 1 degree in lon or lat: 400 (list: `research\gem\places_wide_spread.csv`)
- places split by point groups (1 km): 3,368 (list: `research\gem\places_split_by_point.csv`)
- blocks with 0 MW: [('G100001094818', 'China Coal Bengbu power station', 'oil/gas', 'pre-construction', 'China'), ('G100001023514', 'Guodian Chaohu Distributed Gas power station', 'oil/gas', 'cancelled - inferred 4 y', 'China')]
- country names in the data: 226
