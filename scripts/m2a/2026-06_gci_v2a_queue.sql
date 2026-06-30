-- =============================================================================
-- Migration: GCI v2.0 — Milestone 2a, interconnection_queue table
-- File:      migrations/2026-06_gci_v2a_queue.sql
-- Spec:      SPEC_GCI_v2_0_M2a_pipeline.md §3
--
-- ADDITIVE ONLY. IDEMPOTENT — safe to run multiple times.
-- Does NOT touch indices.grid_constraint, indices.grid_feasibility_current,
-- or any existing infrastructure_raw.* table.
--
-- uuid-генерация: gen_random_uuid() — для консистентности с M1
-- (все 6 таблиц infrastructure_raw/indices.grid_constraint из M1 уже
-- используют gen_random_uuid(), не uuid_generate_v4()).
-- =============================================================================

create table if not exists infrastructure_raw.interconnection_queue (
  id                uuid primary key default gen_random_uuid(),
  source            text not null,              -- 'LBNL_QueuedUp_thru2024_v2'
  source_id         text not null,              -- q_id из Berkeley датафайла
  project_name      text,
  iso               text,                       -- 'PJM' для VA (поле "region" в источнике)
  status            text,                       -- raw q_status: active/withdrawn/operational/suspended
  fuel_type         text,                       -- type1 (или type_clean) из источника
  poi_request_mw    numeric,                    -- max(mw1,mw2,mw3), игнорируя 'NA' (правило §4.3 — не сумма гибрида)
  county_raw        text,                       -- для аудита; матчинг региона — по fips_codes, не по тексту
  state_raw         text,
  entered_date      date,                       -- q_date, конвертация из Excel-serial
  geom              geometry(Point, 4326),      -- источник не содержит lat/lon → NULL для всех VA-строк (см. raw_attributes.geo_method)
  region_id         uuid references core.regions(id),
  raw_attributes    jsonb not null default '{}'::jsonb,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint queue_uniq unique (source, source_id)
);

create index if not exists idx_queue_region
  on infrastructure_raw.interconnection_queue (region_id);

create index if not exists idx_queue_geom
  on infrastructure_raw.interconnection_queue using gist (geom);

create index if not exists idx_queue_iso_status
  on infrastructure_raw.interconnection_queue (iso, status);

-- Переиспользуем существующий триггер из M1 (infrastructure_raw.set_region_from_point).
-- Источник не даёt lat/lon → geom будет NULL для всех VA-записей → триггер
-- молча НЕ перезапишет region_id (см. условие "if new.geom is not null" в M1-функции),
-- то есть region_id, выставленный Python-скриптом через прямой FIPS-лукап,
-- сохранится как есть. Триггер остаётся на случай будущих источников с координатами.
drop trigger if exists trg_interconnection_queue_set_region
  on infrastructure_raw.interconnection_queue;
create trigger trg_interconnection_queue_set_region
  before insert or update on infrastructure_raw.interconnection_queue
  for each row execute function infrastructure_raw.set_region_from_point();

-- НЕ экспонируем в Data API (как вся infrastructure_raw) — никаких grants anon/authenticated.
