-- =============================================================================
-- Patch: GCI v2.0 M2a — line->region trigger fix for infrastructure_raw.transmission_lines
-- File:  migrations/2026-06_gci_v2a_fix_transmission_trigger.sql
--
-- НАХОДКА (не поймана pre-flight): infrastructure.powerlines_set_regions()
-- обращается к NEW.geometry (имя колонки в исходной infrastructure.powerlines,
-- v1.0). Наша infrastructure_raw.transmission_lines (M1-миграция) использует
-- конвенцию geom — как и все остальные таблицы infrastructure_raw.*.
-- Прямое переиспользование функции падает: "record new has no field geometry".
--
-- Pre-flight подтвердил СУЩЕСТВОВАНИЕ и СИГНАТУРУ функции, но не проверял
-- тело на конкретное имя колонки — слепое пятно для будущих pre-flight чеклистов.
--
-- Решение: тонкая wrapper-функция в infrastructure_raw (по аналогии с уже
-- существующей set_region_from_point), повторяющая ту же ST_Intersects-логику,
-- но обращающаяся к NEW.geom. Существующая infrastructure.powerlines_set_regions
-- не трогается — она по-прежнему обслуживает infrastructure.powerlines.
--
-- ADDITIVE, IDEMPOTENT.
-- =============================================================================

create or replace function infrastructure_raw.set_regions_from_line()
returns trigger
language plpgsql
as $$
begin
  if new.geom is not null then
    select array_agg(id) into new.region_ids
    from core.regions
    where ST_Intersects(geometry, new.geom);
  end if;
  return new;
end;
$$;

drop trigger if exists trg_transmission_lines_set_region
  on infrastructure_raw.transmission_lines;
create trigger trg_transmission_lines_set_region
  before insert or update on infrastructure_raw.transmission_lines
  for each row execute function infrastructure_raw.set_regions_from_line();
