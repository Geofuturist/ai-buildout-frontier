r"""
build_layer_substations_osm.py
=================================
ТЗ-1, слой 4/5: "подстанции по данным OpenStreetMap" -- CONUS.

Источник -- OpenStreetMap (power=substation), через Overpass API, не HIFLD:
HIFLD Electric Substations недоступен без формального DUA после закрытия
HIFLD Open в августе 2025 (см. решение в чате -- 4 независимых пути
проверены, все в тупик). Прецедент в проекте уже есть:
Virginia_power_substation_osm.shp был получен тем же способом.

Решения RES (зафиксированы, не подлежат пересмотру без явного решения):
  1. Отдельный слой, назван по источнику -- не "подстанции", а именно OSM.
  2. Отсутствие тега voltage != ноль. n_substations считает ВСЕ объекты;
     max_substation_voltage_kv -- максимум ТОЛЬКО среди известных voltage
     (NaN, если неизвестен у всех, не 0).
  3. frac_substations_voltage_unknown по округу -- диагностика полноты.
  4. known_gaps: n_substations в редконаселённых округах систематически
     занижен -- плотность картирования OSM коррелирует с населением, это
     свойство источника, не дефект пайплайна.
  -- Лицензия ODbL (OSM) vs публикация под CC BY 4.0 -- НЕ решается здесь.
     Помечено в meta.json как открытый вопрос для [ARCH] перед публикацией,
     расчёт это не блокирует.

voltage: OSM Wiki (Key:voltage) подтверждает -- значения в ВОЛЬТАХ, без
единиц/разделителей, несколько уровней через ';'. Берём максимум, делим на
1000 для kV.

Механика: 49 штатов CONUS по отдельности (bbox из границ округов + небольшой
запас), пауза между запросами, кэш сырых ответов на диск -- повторный запуск
пропускает уже полученные штаты, а не начинает с нуля.

Запуск (та же папка, что и gci_conus_common.py):
    python build_layer_substations_osm.py
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from gci_conus_common import (
    CONUS_STATES_FIPS,
    load_conus_counties,
    resolve_points_to_counties,
    write_layer_outputs,
    log,
)

CACHE_DIR = Path(r"C:\Users\PGS\Documents\AI\AI Buildup Frontier project\data\conus\_osm_cache")
LAYER_NAME = "substations_osm"
SOURCE_URL = "https://www.openstreetmap.org (via Overpass API, overpass-api.de)"

OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"
# Основной overpass-api.de сейчас агрессивно режет программные запросы (406,
# затем сброс соединения) -- это статичная блокировка по "виду" клиента, не
# по текущей нагрузке, повторные попытки на тот же сервер не помогают
# (подтверждено внешним источником, апрель-июнь 2026). kumi.systems --
# рекомендованное рабочее зеркало, не требует регистрации. Оставляю адрес
# основного сервера закомментированным как fallback на случай, если зеркало
# когда-нибудь ляжет:
# OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_HEADERS = {
    "User-Agent": "AIBuildoutFrontier-ResearchTool/1.0 (independent research project)",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
}
BBOX_PAD_DEG = 0.1  # запас на границах штата, дедуп по osm id снимает риск задвоения
REQUEST_TIMEOUT_S = 180
DELAY_BETWEEN_REQUESTS_S = 2.0
BOUNDARY_FALLBACK_M = 1000.0  # тот же порог, что и для generation -- откалиброван эмпирически там


def overpass_query(south: float, west: float, north: float, east: float) -> str:
    return f"""
[out:json][timeout:170];
(
  node["power"="substation"]({south},{west},{north},{east});
  way["power"="substation"]({south},{west},{north},{east});
);
out center tags;
""".strip()


def fetch_state(state_fips: str, bbox: tuple[float, float, float, float], max_attempts: int = 2) -> list[dict]:
    """bbox = (south, west, north, east). Кэш на диск -- повторный запуск
    не бьёт по Overpass второй раз за уже полученный штат.

    max_attempts: публичный Overpass сейчас нестабилен под нагрузкой
    (504 Gateway Timeout, разрывы соединения — не наша вина, не блокировка
    по заголовкам, это уже пройденный этап). Пара попыток с паузой ловит
    часть таких сбоев в рамках одного запуска, не заставляя перезапускать
    весь скрипт вручную ради каждого упавшего штата."""
    import requests

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"substations_{state_fips}.json"

    if cache_path.exists():
        log.info("  [%s] из кэша: %s", state_fips, cache_path.name)
        with open(cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)["elements"]

    south, west, north, east = bbox
    query = overpass_query(south, west, north, east)

    for attempt in range(1, max_attempts + 1):
        log.info(
            "  [%s] запрос к Overpass (попытка %d/%d, bbox=%.2f,%.2f,%.2f,%.2f)...",
            state_fips, attempt, max_attempts, south, west, north, east,
        )
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, headers=OVERPASS_HEADERS, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if attempt < max_attempts:
                backoff = 15.0 * attempt
                log.warning("  [%s] попытка %d не удалась (%s), жду %.0fс и пробую снова...", state_fips, attempt, e, backoff)
                time.sleep(backoff)
                continue
            log.error("  [%s] ОШИБКА после %d попыток: %s — пропускаю в этом запуске.", state_fips, max_attempts, e)
            return []

        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        log.info("  [%s] получено %d объектов, закэшировано.", state_fips, len(data.get("elements", [])))
        return data.get("elements", [])

    return []


def parse_voltage_kv(voltage_tag) -> float | None:
    """OSM: вольты, без единиц, несколько уровней через ';'. Максимум -> kV.
    Подтверждено по OSM Wiki Key:voltage."""
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


def elements_to_records(elements: list[dict]) -> list[dict]:
    records = []
    for el in elements:
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        elif el["type"] == "way":
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        else:
            continue
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        records.append({
            "osm_type": el["type"],
            "osm_id": el["id"],
            "lat": lat,
            "lon": lon,
            "name": tags.get("name"),
            "operator": tags.get("operator"),
            "voltage_raw": tags.get("voltage"),
            "voltage_kv": parse_voltage_kv(tags.get("voltage")),
        })
    return records


def main() -> None:
    import pandas as pd
    import geopandas as gpd

    counties = load_conus_counties()
    counties_wgs84 = counties.to_crs("EPSG:4326")

    log.info("Запрашиваю подстанции по %d штатам CONUS (Overpass, по одному)...", len(CONUS_STATES_FIPS))
    all_records: list[dict] = []
    succeeded_fips: set[str] = set()
    for i, state_fips in enumerate(sorted(CONUS_STATES_FIPS), 1):
        state_counties = counties_wgs84[counties_wgs84["STATEFP"] == state_fips]
        if state_counties.empty:
            continue
        minx, miny, maxx, maxy = state_counties.total_bounds
        bbox = (miny - BBOX_PAD_DEG, minx - BBOX_PAD_DEG, maxy + BBOX_PAD_DEG, maxx + BBOX_PAD_DEG)

        was_cached = (CACHE_DIR / f"substations_{state_fips}.json").exists()
        elements = fetch_state(state_fips, bbox)
        if (CACHE_DIR / f"substations_{state_fips}.json").exists():
            succeeded_fips.add(state_fips)
        all_records.extend(elements_to_records(elements))

        if not was_cached:
            time.sleep(DELAY_BETWEEN_REQUESTS_S)

        if i % 10 == 0:
            log.info("Прогресс: %d/%d штатов обработано.", i, len(CONUS_STATES_FIPS))

    missing_fips = CONUS_STATES_FIPS - succeeded_fips
    if missing_fips:
        log.error("=" * 78)
        log.error(
            "ПОКРЫТИЕ НЕПОЛНОЕ: %d/%d штатов получены, %d отсутствуют: %s",
            len(succeeded_fips), len(CONUS_STATES_FIPS), len(missing_fips), sorted(missing_fips),
        )
        log.error(
            "Финальные файлы слоя НЕ записаны — иначе отсутствующие штаты выглядели бы как "
            "'0 подстанций', что неправда, это 'нет ответа от Overpass', разные вещи."
        )
        log.error(
            "Запустите скрипт ещё раз (уже полученные %d штатов возьмутся из кэша, не будут "
            "перезапрошены) — повторяйте, пока это сообщение не перестанет появляться.",
            len(succeeded_fips),
        )
        log.error("=" * 78)
        return

    log.info("Покрытие полное: все %d штатов получены.", len(CONUS_STATES_FIPS))
    log.info("Всего элементов получено (до дедупликации): %d", len(all_records))

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["osm_type", "osm_id"])
    log.info("После дедупликации по osm_type+osm_id: %d", len(df))

    points = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    points = points.to_crs(counties.crs)

    log.info("Point-in-polygon (строгий + ближайший <=%.0fм)...", BOUNDARY_FALLBACK_M)
    joined, n_unresolved = resolve_points_to_counties(points, counties, fallback_buffer_m=BOUNDARY_FALLBACK_M)
    if n_unresolved:
        log.warning("%d подстанций не резолвлены даже с запасом — исключены.", n_unresolved)
    joined = joined[joined["fips"].notna()].copy()

    joined["has_voltage"] = joined["voltage_kv"].notna()

    agg = joined.groupby("fips").agg(
        n_substations=("osm_id", "count"),
        n_with_voltage=("has_voltage", "sum"),
        max_substation_voltage_kv=("voltage_kv", "max"),
    ).reset_index()
    agg["frac_substations_voltage_unknown"] = 1 - (agg["n_with_voltage"] / agg["n_substations"])

    result = counties.merge(agg, on="fips", how="left")
    result["n_substations"] = result["n_substations"].fillna(0).astype(int)
    # max_substation_voltage_kv и frac_..._unknown остаются NaN там, где n_substations==0 --
    # это осознанно: "нет подстанций" и "подстанции есть, voltage неизвестен у всех" -- разные факты.

    n_zero = int((result["n_substations"] == 0).sum())
    log.info("Округов без единой подстанции (OSM): %d/%d", n_zero, len(result))

    snapshot_date = dt.date.today().strftime("%Y%m%d")
    meta = {
        "source": "OpenStreetMap, тег power=substation (через Overpass API)",
        "source_url": SOURCE_URL,
        "vintage": f"снимок на дату запуска скрипта: {snapshot_date}",
        "license": (
            "OpenStreetMap — ODbL (Open Database License). Проект публикует данные под CC BY 4.0 — "
            "совместимость ODbL (share-alike) с CC BY для этого производного слоя НЕ решена здесь, "
            "открытый вопрос для [ARCH] перед публикацией. Расчёт слоя это не блокирует."
        ),
        "coverage": "48 states + DC (CONUS)",
        "n_units_covered": int(len(joined)),
        "n_units_no_data": n_unresolved,
        "known_gaps": (
            "n_substations в редконаселённых округах систематически занижен — плотность картирования "
            "OSM коррелирует с населением, это свойство источника, не дефект пайплайна. "
            "max_substation_voltage_kv — максимум ТОЛЬКО среди подстанций с известным тегом voltage; "
            "отсутствие тега не равно нулю, такие объекты учтены в n_substations, но не в max(). "
            "frac_substations_voltage_unknown по каждому округу — доля подстанций без известного "
            "напряжения, для оценки надёжности max_substation_voltage_kv в конкретном округе."
        ),
    }

    write_layer_outputs(
        LAYER_NAME,
        result[["fips", "NAME", "NAMELSAD", "n_substations", "max_substation_voltage_kv",
                 "frac_substations_voltage_unknown", "geometry"]],
        meta,
        snapshot_date,
    )
    log.info("ГОТОВО.")


if __name__ == "__main__":
    main()
