# boundaries — сборка границ ABF (`abf-boundaries-v0.2.0`)

Пайплайн ADM0 (мир) + ADM1/ADM2 (США, Франция, Британия, Норвегия) на каркасе Natural Earth
1:10m. С v0.2.0 добавлены: ADM1 ещё 104 стран по плану (`adm1_plan.csv`), Аджария в ADM0 Грузии
(`adm0_patches.csv`), названия Франции (`name_overrides.csv`), слой `contested_areas`. Спецификация и решения — `SPEC_BND_boundaries_v0_1.md`, `ARCHITECTURE_DECISIONS_v6.md`
(в проекте claude.ai, не в этом репозитории); для v0.2.0 — `SPEC_BND_boundaries_v0_2_0.md`. Точные команды и числа
релиза — `CODE_to_ARCH_handoff_BND_v0_2_0.md`.

## Файлы

| Файл | Назначение |
|---|---|
| `scripts/boundaries/bnd_common.py` | общий модуль, напрямую не запускается |
| `scripts/boundaries/bnd_plan.py` | v0.2.0: построитель ADM1 по плану, патч ADM0, имена, вложенные единицы (П8), покрытие суши, `contested_areas`, сверка с прошлым выпуском; напрямую не запускается |
| `scripts/boundaries/fetch_boundary_sources.py` | скачивает/проверяет исходные данные; с v0.2.0 — и четыре файла Unicode CLDR release-48-2 (SHA-256 заданы в скрипте, расхождение — остановка) |
| `scripts/boundaries/fix_registry_notes.py` | v0.2.0, одноразовый: правит тексты `notes` реестра (20 стран) до сборки; сверяет, что остальное не изменилось; повторный запуск останавливается (старого текста уже нет) |
| `scripts/boundaries/build_boundaries.py` | сборка |
| `scripts/boundaries/validate_boundaries.py` | проверка (11 проверок; код выхода 1 при провале 1–5 и 7–11; 6 — справочная) |
| `scripts/boundaries/make_registry_template.py` | вспомогательный список стран для реестра; в сборке не используется |
| `boundaries/boundary_registry.csv` | реестр методов сборки по странам (правится вручную) |
| `boundaries/adm0_overrides.csv` | таблица переопределений ADM0 при `ISO_A3_EH == "-99"` (SPEC §4.1) |
| `boundaries/adm1_plan.csv` | v0.2.0: план ADM1 — 1 578 единиц 104 стран (`unit_id`, код ISO, английское название CLDR, коды NE, метод); из `abf-scratch` `f877a30`, строки `decision = release` |
| `boundaries/adm1_leftovers.csv` | v0.2.0: части ADM0 без ADM1 (правило П7(б)), 10 строк; справочно, в сборке не используется |
| `boundaries/code_overrides.csv` | v0.2.0: исправления кодов CLDR/NE; справочно (план уже их учитывает) |
| `boundaries/adm0_patches.csv` | v0.2.0: исправления ADM0 (сейчас одна строка — Аджария в Грузию); только перечисленное, автоматики «к ближайшей стране» нет |
| `boundaries/name_overrides.csv` | v0.2.0: исправленные названия (Франция — 6 строк; `CHN-1-NM` «Inner Mongolia» по CLDR — 7-я); применяются к `name` всех уровней |
| `boundaries/contested_areas.csv` | v0.2.0: слой «фактический контроль» (строки пишет RES; сборка файл не правит; пустой файл допустим) |
| `boundaries/code_crosswalk_exact.csv` | таблица смены кодов США (справочно) |
| `boundaries/holes_whitelist.geojson` | белый список дыр ADM0; появляется после `--init-whitelist`, в git — после того как ты посмотрел его в QGIS |

## Установка (один раз)

`pip` у тебя не в PATH (см. pre-flight §7.6) — везде `python -m pip`:

```
python -m pip install "geopandas>=1.0" "shapely>=2.0" pyogrio pyarrow pyproj requests
```

## Запуск (из корня репозитория, PowerShell)

```
python scripts\boundaries\fetch_boundary_sources.py --sources-dir "D:\GISData\Boundaries\sources"

python scripts\boundaries\build_boundaries.py --sources-dir "D:\GISData\Boundaries\sources" --out-dir "D:\GISData\Boundaries\out\abf-boundaries-v0.2.0" --pov usa

python scripts\boundaries\validate_boundaries.py --out-dir "D:\GISData\Boundaries\out\abf-boundaries-v0.2.0" --sources-dir "D:\GISData\Boundaries\sources" --prev-hashes "D:\GISData\Boundaries\out\abf-boundaries-v0.1.0\unit_hashes.csv"

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

Файл `holes_whitelist.geojson` уже в git: с v0.2.0 `--init-whitelist` в обычном запуске не нужен (флаг нужен только для
пересчёта белого списка после смены ADM0; он перезаписывает файл).

### Полная последовательность выпуска v0.2.0

Слой `display/adm0_disputed_unassigned.{parquet,geojson.gz}` (пять спорных территорий без страны) сам
`build_boundaries.py` в v0.2.0 не пишет. Его пишет `validate_boundaries.py --write-disputed-layer`
из закоммиченного `holes_whitelist.geojson` (ничего не пересчитывается, белый список не меняется).
Без него `build_release.py` останавливается на G4. Порядок:

0. Перед сборкой: свежий клон или `git pull` ветки `main`, затем `git status` и `git diff main -- boundaries scripts\boundaries`.
   Файлы, которые собираешься менять, должны совпадать с `main` по `git diff`, а не по памяти локальной копии
   (иначе чужие правки из `main` молча откатываются).
1. `fetch_boundary_sources.py --sources-dir ...` (кэш: уже лежащее не трогается; четыре файла CLDR проверяются по SHA-256).
2. `build_boundaries.py --sources-dir ... --out-dir ...\abf-boundaries-v0.2.0 --pov usa`
3. Один запуск проверки, который заодно пишет слой спорных территорий:

```
python scripts\boundaries\validate_boundaries.py --out-dir "D:\GISData\Boundaries\out\abf-boundaries-v0.2.0" --sources-dir "D:\GISData\Boundaries\sources" --prev-hashes "D:\GISData\Boundaries\out\abf-boundaries-v0.1.0\unit_hashes.csv" --write-disputed-layer
```

   В выводе: первая строка `wrote display/adm0_disputed_unassigned.* (7 zones, pov=usa)`, в конце `OVERALL: PASSED`.
4. Результат: в `display\` десять файлов (`adm0`, `adm1`, `adm2`, `contested_areas`, `adm0_disputed_unassigned`; у каждого `.parquet` и `.geojson.gz`),
   рядом `analysis\`, `meta.json`, `build_log.json`, `validation_report.json/.md`, `unit_hashes.csv`.
5. Сверка со второй средой (по желанию): сравнить два `unit_hashes.csv` по `unit_id`, `geom_sha256_16`, `attr_sha256_16`.
   Для v0.2.0 облако и Windows дали 5 511 из 5 511 совпавших строк.

В следующей версии запись слоя переедет в `build_boundaries.py` (SPEC r5 §2.8), и шаг 3 останется чистой проверкой.

## Что посмотреть в QGIS после сборки

- `boundaries/holes_whitelist.geojson` (после `--init-whitelist`, до того как класть в git) —
  12 дыр ADM0, у каждой `label`/`kind`; `"UNKNOWN -- review in QGIS"` быть не должно.
- `validation_report.md` в `--out-dir` — проверки 1–5 и 7–11 должны быть `PASSED` (проверка 1: допуск 0,05 км² только для пар ADM1 из разных стран, где одна — USA/NOR; все пары > 0,01 км² перечислены в отчёте); проверка 6 —
  справочная, список несовпадений не проваливает сборку. В `validation_report.json`: острова NE admin-1
  вне ADM0 (проверка 7), таблица вложенных единиц (проверка 8), потери ADM1 при обрезке по стране
  (`plan_adm1_clip_losses`), сверка с v0.1.0 (проверка 9, нужен `--prev-hashes`), коды и названия по CLDR (проверка 11; в отчёте одна строка — `SHN-1-TA`).
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
