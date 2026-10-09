# boundaries — сборка границ ABF (`abf-boundaries-v0.1.0`)

Пайплайн ADM0 (мир) + ADM1/ADM2 (США, Франция, Британия, Норвегия) на каркасе Natural Earth
1:10m. Спецификация и решения — `SPEC_BND_boundaries_v0_1.md`, `ARCHITECTURE_DECISIONS_v6.md`
(в проекте claude.ai, не в этом репозитории). Точные команды и числа этого релиза —
`CODE_to_ARCH_handoff_BND_v0_1.md`.

## Файлы

| Файл | Назначение |
|---|---|
| `scripts/boundaries/bnd_common.py` | общий модуль, напрямую не запускается |
| `scripts/boundaries/fetch_boundary_sources.py` | скачивает/проверяет исходные данные |
| `scripts/boundaries/build_boundaries.py` | сборка |
| `scripts/boundaries/validate_boundaries.py` | проверка (6 проверок, код выхода 1 при провале 1–5) |
| `scripts/boundaries/make_registry_template.py` | вспомогательный список стран для реестра; в сборке не используется |
| `boundaries/boundary_registry.csv` | реестр методов сборки по странам (правится вручную) |
| `boundaries/adm0_overrides.csv` | таблица переопределений ADM0 при `ISO_A3_EH == "-99"` (SPEC §4.1) |
| `boundaries/holes_whitelist.geojson` | белый список дыр ADM0; появляется после `--init-whitelist`, в git — после того как ты посмотрел его в QGIS |

## Установка (один раз)

`pip` у тебя не в PATH (см. pre-flight §7.6) — везде `python -m pip`:

```
python -m pip install "geopandas>=1.0" "shapely>=2.0" pyogrio pyarrow pyproj requests
```

## Запуск (из корня репозитория, PowerShell)

```
python scripts\boundaries\fetch_boundary_sources.py --sources-dir "D:\GISData\Boundaries\sources"

python scripts\boundaries\build_boundaries.py --sources-dir "D:\GISData\Boundaries\sources" --out-dir "D:\GISData\Boundaries\out\abf-boundaries-v0.1.0" --pov usa

python scripts\boundaries\validate_boundaries.py --out-dir "D:\GISData\Boundaries\out\abf-boundaries-v0.1.0" --sources-dir "D:\GISData\Boundaries\sources" --init-whitelist

python scripts\boundaries\validate_boundaries.py --out-dir "D:\GISData\Boundaries\out\abf-boundaries-v0.1.0" --sources-dir "D:\GISData\Boundaries\sources"

python scripts\boundaries\make_registry_template.py --sources-dir "D:\GISData\Boundaries\sources" --out boundaries\boundary_registry_template.csv
```

Отличие от команд SPEC §7: `validate_boundaries.py` требует `--sources-dir` в обоих запусках (не
только для необязательной проверки 6, как было в SPEC §7, а и для обязательной проверки 3 — ей
нужен `ne_10m_lakes`). Раньше при отсутствии флага скрипт падал на проверке 3 с невнятной causой;
теперь `--sources-dir` обязателен, и это видно сразу из `--help`. Подробности — в сдаточном отчёте,
п. 2.

Census (`cb_2023_us_state_500k.zip`, `cb_2023_us_county_500k.zip`) и оба файла Kartverket
`fetch_boundary_sources.py` сам не скачает — при их отсутствии скрипт печатает, какого файла не
хватает и где его взять, и останавливается без запуска сборки. Положи файл в `--sources-dir` под
именем, которое напечатал скрипт, и запусти `fetch_boundary_sources.py` ещё раз (кэш: то, что уже
скачано или уже лежит на месте, второй раз не трогается).

## Что посмотреть в QGIS после сборки

- `boundaries/holes_whitelist.geojson` (после `--init-whitelist`, до того как класть в git) —
  12 дыр ADM0, у каждой `label`/`kind`; `"UNKNOWN -- review in QGIS"` быть не должно.
- `validation_report.md` в `--out-dir` — проверки 1–5 должны быть `PASSED`; проверка 6 —
  справочная, список несовпадений не проваливает сборку.
- `display/adm1.parquet` и `analysis/NOR_adm1_inndelingsbase_20260101.parquet` — граница Норвегии
  у соседей (Швеция, Финляндия, Россия) и Шпицберген.
- `display/adm1.parquet` и `analysis/USA_adm1_cb2023_500k.parquet` — граница США у Канады и Мексики.

## Повторяемость (SPEC §8)

Повторный запуск `build_boundaries.py` в одной и той же среде должен дать побайтово тот же
`unit_hashes.csv`. Между облаком исполнителя и твоим Windows побайтового совпадения не требуется
(разные версии GEOS) — достаточно совпадения набора `unit_id` и площади каждой единицы в пределах
0,01%.

## `.gitignore`

Блок `*.geojson` исключает геометрию из git — это верно (SPEC требует не коммитить геометрию), но
заодно исключает и `boundaries/holes_whitelist.geojson`, который SPEC §6 явно требует закоммитить
после согласования. Добавь одну строку рядом с уже существующей `!public/**/*.geojson`:

```
!boundaries/holes_whitelist.geojson
```

`boundary_registry.csv` и `adm0_overrides.csv` этот блок не касается — `.csv` нигде не исключён,
закоммитятся как обычные текстовые файлы.
