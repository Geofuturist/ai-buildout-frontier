'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import MapCanvas from './MapCanvas';
import type { MapHandle } from './MapCanvas';
import LegendCard from './LegendCard';
import TerritoryPanel from './TerritoryPanel';
import InfoCard from './InfoCard';
import MapNav from './MapNav';
import { MODULE_BY_TYPE } from './modules';
import { selectDataLayers } from './select';
import type { CardState, MapData, UnitRef } from './types';
import { countryNameFromIso3 } from '@/lib/iso3';
import { buildCountries, fillLevelOf, levelWord, selectionLevel } from '@/lib/indicators';
import { WORLD, groupByCountry, unionBbox } from '@/lib/layers';
import { buildRows } from '@/lib/panel';
import type { PanelRow } from '@/lib/panel';
import { isWithin, levelsOfCountry, loadTerritory } from '@/lib/territory';
import type { Territory } from '@/lib/territory';

export default function MapApp({ data }: { data: MapData }) {
  const mapRef = useRef<MapHandle>(null);
  const [country, setCountry] = useState<string | null>(null);
  // null = the country itself is chosen
  const [unit, setUnit] = useState<UnitRef | null>(null);
  const [indicatorKey, setIndicatorKey] = useState<string | null>(null);
  const [overlays, setOverlays] = useState<Record<string, boolean>>({});
  const [card, setCard] = useState<CardState>(null);
  const [failed, setFailed] = useState<Set<string>>(new Set());
  const [territory, setTerritory] = useState<Territory | null>(null);
  const [zoom, setZoom] = useState(1.5);
  const [nonce, setNonce] = useState(0);

  const onFailed = useCallback((id: string) => setFailed((prev) => (prev.has(id) ? prev : new Set(prev).add(id))), []);

  const layers = useMemo(() => selectDataLayers(data), [data]);
  const allModels = useMemo(
    () => buildCountries(groupByCountry(layers, data.metas, data.default_layer), data.metas, (l) => MODULE_BY_TYPE[l.tiles.geometry_type].exclusive),
    [layers, data.metas, data.default_layer],
  );
  // Layers that cover several countries (coverage.iso3 with 2+ codes) are not tied to a country
  const worldModel = allModels.find((c) => c.iso3 === WORLD) ?? null;
  const countries = useMemo(() => allModels.filter((c) => c.iso3 !== WORLD), [allModels]);
  const rows = useMemo(() => buildRows(worldModel, countries, data.metas), [worldModel, countries, data.metas]);

  const model = countries.find((c) => c.iso3 === country) ?? null;
  const countryName = model?.name ?? (country ? countryNameFromIso3(country) : '');
  // The fill that is on: any country's indicator or a world one; it does not depend on the chosen country
  const indicator = indicatorKey ? rows.find((r) => r.indicator?.key === indicatorKey)?.indicator ?? null : null;
  const indCountry = indicator && indicator.iso3 !== WORLD ? indicator.iso3 : null;

  // Level a click selects, from the zoom; the fill is the finest layer of the indicator not finer than that
  const selLevel = selectionLevel(zoom, data.level_zoom, levelsOfCountry(territory, indCountry ?? country ?? ''));
  const fill = indicator ? fillLevelOf(indicator, selLevel) : null;
  const activeId = fill?.layer.layer_id ?? 'none';
  // No data at this level: plain polygons of the level are drawn instead of a layer of another level
  const neutralLevel = indCountry && !fill ? selLevel : null;
  const neutralIds = useMemo(() => {
    if (neutralLevel === null || !indCountry) return [];
    if (neutralLevel === 0) return [indCountry];
    if (!territory) return [];
    return Object.entries(territory.units)
      .filter(([id, u]) => u[0] === neutralLevel && isWithin(territory, id, indCountry))
      .map(([id]) => id);
  }, [neutralLevel, indCountry, territory]);
  const dataCountryIds = useMemo(() => countries.map((c) => c.iso3), [countries]);
  const chosen: UnitRef | null = country ? unit ?? { unit_id: country, name: countryName, level: 0 } : null;

  // Points and lines that are switched on are drawn wherever they are, whatever country is chosen
  const overlaysOn = useMemo(() => layers.filter((l) => !MODULE_BY_TYPE[l.tiles.geometry_type].exclusive && overlays[l.layer_id]), [layers, overlays]);
  const shownOverlays: Record<string, boolean> = Object.fromEntries(overlaysOn.map((l) => [l.layer_id, true]));

  const ensureTerritory = useCallback(() => {
    loadTerritory().then(setTerritory).catch(() => undefined);
  }, []);

  /**
   * Choose a country (a click on the map or a layer of that country). Fill rule: no fill on, or a fill of another
   * country -> the default indicator of this country turns on; a world fill stays; a country with no layers of its
   * own leaves the fill as it is. `fly` moves the map to the country's layers.
   */
  const selectCountry = useCallback(
    (iso3: string, opts?: { key?: string; fly?: [number, number, number, number] | null }) => {
      const m = countries.find((c) => c.iso3 === iso3);
      setCountry(iso3);
      setUnit(null);
      setCard(null);
      setNonce((n) => n + 1);
      ensureTerritory();
      let key = opts?.key ?? indicatorKey;
      let fly = opts?.fly ?? null;
      if (!opts?.key && m && m.indicators.length) {
        const keep = indicator && (indicator.iso3 === WORLD || indicator.iso3 === iso3);
        if (!keep) {
          const byDefault = data.default_layer ? m.indicators.find((i) => i.levels.some((x) => x.layer.layer_id === data.default_layer)) : undefined;
          const ind = byDefault ?? m.indicators[0];
          key = ind.key;
          fly = unionBbox(ind.levels.map((x) => x.layer), data.metas);
        }
      }
      setIndicatorKey(key);
      if (fly) mapRef.current?.fitBounds(fly);
    },
    [countries, data.default_layer, data.metas, indicator, indicatorKey, ensureTerritory],
  );

  // Panel: a fill switch. A country's layer also chooses that country and flies to it; a world layer changes nothing else.
  const onFill = (row: PanelRow) => {
    if (indicatorKey === row.indicator?.key) {
      setIndicatorKey(null);
      return;
    }
    if (!row.indicator) return;
    if (row.iso3 === WORLD) {
      setIndicatorKey(row.indicator.key);
      return;
    }
    selectCountry(row.iso3, { key: row.indicator.key, fly: unionBbox(row.indicator.levels.map((x) => x.layer), data.metas) });
  };
  const onOverlayRow = (row: PanelRow, on: boolean) => {
    if (!row.layer) return;
    setOverlays((prev) => ({ ...prev, [row.layer!.layer_id]: on }));
    if (on && row.iso3 !== WORLD) {
      const fly = unionBbox([row.layer], data.metas);
      if (country !== row.iso3) selectCountry(row.iso3, { key: indicatorKey ?? undefined, fly });
      else if (fly) mapRef.current?.fitBounds(fly);
    }
  };

  const onUnit = useCallback((u: UnitRef) => {
    setUnit(u.level === 0 ? null : u);
    setCard(null);
    setNonce((n) => n + 1);
    ensureTerritory();
  }, [ensureTerritory]);

  const toWorld = () => {
    setCountry(null);
    setUnit(null);
    setCard(null);
    mapRef.current?.fitWorld();
  };

  // A step of the path: the country or a unit above the chosen one
  const onCrumb = (unitId: string) => {
    if (!country) return;
    if (unitId === country) {
      setUnit(null);
      const b = indicator && indCountry === country ? unionBbox(indicator.levels.map((x) => x.layer), data.metas) : null;
      if (b) mapRef.current?.fitBounds(b);
      return;
    }
    const info = territory?.units[unitId];
    if (!info) return;
    setUnit({ unit_id: unitId, name: info[1], level: info[0] });
    mapRef.current?.fitUnit(unitId, info[0]);
  };

  // The site may open on a country (content/site.json default_view.country)
  const opened = useRef(false);
  const onReady = useCallback(() => {
    if (opened.current) return;
    opened.current = true;
    if (data.default_country) selectCountry(data.default_country);
  }, [data.default_country, selectCountry]);

  // The record of a point or line shown in the card (outline in its module)
  const selected = (() => {
    if (!card || card.type !== 'record') return null;
    const layer = data.layers.find((l) => l.layer_id === card.layerId);
    if (!layer) return null;
    const v = card.props[MODULE_BY_TYPE[layer.tiles.geometry_type].keyField];
    return v === undefined || v === null ? null : { layerId: card.layerId, key: String(v) };
  })();

  // Legend heading: indicator title and the level that is drawn
  const heading = indicator ? `${indicator.title} · ${levelWord(fill ? fill.level : selLevel, indicator, indicator.iso3, data.unit_words)} level` : null;
  const finest = indicator ? indicator.levels[indicator.levels.length - 1] : null;
  const note =
    indicator && !fill && finest
      ? `No data at this level in this release. Zoom in to see ${levelWord(finest.level, indicator, indicator.iso3, data.unit_words).toLowerCase()} data.`
      : null;
  const legendLayers = [...(fill ? [fill.layer] : []), ...overlaysOn];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1">
        <MapCanvas
          ref={mapRef}
          data={data}
          activeId={activeId}
          overlays={shownOverlays}
          selected={selected}
          country={country}
          selectLevel={selLevel}
          selectedUnit={chosen}
          neutralLevel={neutralLevel}
          neutralIds={neutralIds}
          dataCountries={dataCountryIds}
          onSelect={setCard}
          onCountry={(iso3) => selectCountry(iso3)}
          onUnit={onUnit}
          onZoom={setZoom}
          onReady={onReady}
          onFailed={onFailed}
        />
        <LegendCard
          data={data}
          heading={heading}
          note={note}
          layers={legendLayers}
          covered={card !== null}
          nonce={nonce}
          rows={rows}
          activeFill={indicator?.key ?? null}
          overlays={overlays}
          failed={failed}
          onFill={onFill}
          onOverlay={onOverlayRow}
          onInfo={(id) => setCard({ type: 'layer', layerId: id })}
        />
        <MapNav preview={data.channel === 'dev'} />
        {/* Zoom and the level a click selects, above the zoom buttons */}
        <p className="pointer-events-none absolute bottom-[86px] right-[10px] z-10 rounded bg-surface/90 px-1.5 py-0.5 text-[11px] font-semibold text-ink2 max-md:bottom-[62px] max-md:left-[112px] max-md:right-auto" aria-live="off">
          Zoom {zoom.toFixed(1)} · {country ? levelWord(selLevel, indicator ?? undefined, country, data.unit_words) : 'Country'} level
        </p>
        <TerritoryPanel
          data={data}
          countryIso={country}
          countryName={countryName}
          model={model}
          indicator={indicator && country && (indicator.iso3 === WORLD || indicator.iso3 === country) ? indicator : null}
          unit={chosen}
          territory={territory}
          hidden={card !== null}
          nonce={nonce}
          selLevel={selLevel}
          onWorld={toWorld}
          onCrumb={onCrumb}
        />
        <InfoCard data={data} card={card} onClose={() => setCard(null)} />
      </div>

      {/* Always visible, including on a phone (SPEC_WEB 4.6) */}
      <div className="shrink-0 border-t border-line bg-surface px-3 py-1.5 text-[11px] leading-snug text-ink2">
        © <a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a> ©{' '}
        <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>
        {' · '}
        <Link href="/attribution/" className="font-semibold">Sources and licenses</Link>
      </div>
    </div>
  );
}
