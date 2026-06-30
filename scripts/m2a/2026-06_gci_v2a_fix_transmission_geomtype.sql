-- =============================================================================
-- Patch: GCI v2.0 M2a — geometry type fix for infrastructure_raw.transmission_lines
-- File:  migrations/2026-06_gci_v2a_fix_transmission_geomtype.sql
--
-- НАХОДКА (не поймана pre-flight): M1-миграция объявила geom как
-- geometry(LineString, 4326), по образцу infrastructure.powerlines.
-- Реальный HIFLD-источник содержит смесь LineString и MultiLineString
-- (multipart-объекты — обычное дело для HIFLD transmission lines,
-- единый "ID" может состоять из нескольких физических сегментов).
--
-- Pre-flight проверил тип геометрии ОДНОЙ строки через geometry_columns
-- (показал LINESTRING), но не проверял однородность всего источника —
-- второе слепое пятно методики pre-flight, см. также fix_transmission_trigger.
--
-- Решение: расширяем колонку до MultiLineString (ST_Multi конвертирует уже
-- загруженные LineString-геометрии без потери данных — single-part линия
-- становится MultiLineString с одним элементом). Ingestion-скрипт
-- нормализует ВСЕ геометрии в MultiLineString перед записью, чтобы новые
-- INSERT/UPDATE не падали повторно.
--
-- ADDITIVE (расширение типа, не сужение), IDEMPOTENT (ALTER ... TYPE на
-- уже-целевой тип безопасен, ST_Multi от MultiLineString — тождество).
-- =============================================================================

alter table infrastructure_raw.transmission_lines
  alter column geom type geometry(MultiLineString, 4326)
  using ST_Multi(geom);
