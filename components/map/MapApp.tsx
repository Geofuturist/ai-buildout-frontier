'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import MapCanvas from './MapCanvas';
import type { MapHandle } from './MapCanvas';
import LegendCard from './LegendCard';
import TerritoryPanel from './TerritoryPanel';
import WorldCard from './WorldCard';
import Fan from './Fan';
import Legend from './Legend';
import InfoCard from './InfoCard';
import MapNav from './MapNav';
import { MODULE_BY_TYPE } from './modules';
import { selectDataLayers } from './select';
import type { CardState, FanSpot, MapData, UnitRef } from './types';
import { countryNameFromIso3 } from '@/lib/iso3';
import { buildCountries, fillLevelOf, levelWord, selectionLevel } from '@/lib/indicators';
import { WORLD, groupByCountry, unionBbox } from '@/lib/layers';
import { buildRows, colorsOf, inCountry, onMap } from '@/lib/panel';
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
  // The whole world is chosen (a click on the globe far out, or the World step of the path)
  const [worldOpen, setWorldOpen] = useState(false);
  // Filter by operator type: one group at a time, or null for all (display.filter_fields of the places layer)
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  // The place that was clicked and may open as a fan (screen position); it shows only while its own card is open
  const [fanSpot, setFanSpot] = useState<FanSpot | null>(null);

  const onFailed = useCallback((id: string) => setFailed((prev) => (prev.has(id) ? prev : new Set(prev).add(id))), []);

  const layers = useMemo(() => selectDataLayers(data), [data]);
  // Layers with display.map = false are not items of the map: no row, no fill, no points. They stay in the files and
  // the values of the card, so there are two models: of the layers on the map and of all layers (SPEC_DC_world 9 p. 5).
  const mapLayers = useMemo(() => layers.filter((l) => onMap(data.metas[l.meta_id])), [layers, data.metas]);
  const modelsOf = useCallback(
    (ls: typeof layers) => buildCountries(groupByCountry(ls, data.metas, data.default_layer), data.metas, (l) => MODULE_BY_TYPE[l.tiles.geometry_type].exclusive),
    [data.metas, data.default_layer],
  );
  const allModels = useMemo(() => modelsOf(mapLayers), [modelsOf, mapLayers]);
  const fullModels = useMemo(() => modelsOf(layers), [modelsOf, layers]);
  // Layers that cover several countries (coverage.iso3 with 2+ codes) are not tied to a country
  const worldModel = allModels.find((c) => c.iso3 === WORLD) ?? null;
  const fullWorld = fullModels.find((c) => c.iso3 === WORLD) ?? null;
  const countries = useMemo(() => allModels.filter((c) => c.iso3 !== WORLD), [allModels]);
  const rows = useMemo(() => buildRows(worldModel, countries, data.metas), [worldModel, countries, data.metas]);
  // The panel on the left lists the layers of the whole world; the layers of one country are chosen in its card
  const worldRows = useMemo(() => rows.filter((r) => r.iso3 === WORLD), [rows]);
  // The card of a country lists the families that have a layer of that country (a world family too, if it has one)
  const countryRows = useMemo(() => rows.filter((r) => country !== null && inCountry(r, country)), [rows, country]);

  const model = countries.find((c) => c.iso3 === country) ?? null;
  const fullModel = fullModels.find((c) => c.iso3 === country) ?? null;
  // Indicators that are not on the map (map = false): their values stay in the card of the country
  const hiddenInds = useMemo(
    () => [...(fullWorld?.indicators ?? []), ...(fullModel?.indicators ?? [])].filter((i) => !onMap(data.metas[i.levels[0].layer.meta_id])),
    [fullWorld, fullModel, data.metas],
  );
  const countryName = (country ? data.countries.find((c) => c.iso3 === country)?.name : undefined) ?? model?.name ?? (country ? countryNameFromIso3(country) : '');
  // The fill that is on: any country's indicator or a world one; it does not depend on the chosen country
  const indicator = indicatorKey ? rows.flatMap((r) => r.fills).find((i) => i.key === indicatorKey) ?? null : null;
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
  const overlaysOn = useMemo(() => mapLayers.filter((l) => !MODULE_BY_TYPE[l.tiles.geometry_type].exclusive && overlays[l.layer_id]), [mapLayers, overlays]);
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
      setWorldOpen(false);
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
          fly = fly ?? unionBbox(ind.levels.map((x) => x.layer), data.metas);
        }
      }
      setIndicatorKey(key);
      if (fly) mapRef.current?.fitBounds(fly);
    },
    [countries, data.default_layer, data.metas, indicator, indicatorKey, ensureTerritory],
  );

  // Panel: the Colors switch of a family. A fill of a country also chooses that country and flies to it; a world fill
  // changes nothing else. The fill is the one of the chosen country when the family has several.
  const onColors = (row: PanelRow) => {
    const ind = colorsOf(row, country);
    if (!ind) return;
    if (indicatorKey === ind.key) {
      setIndicatorKey(null);
      return;
    }
    if (ind.iso3 === WORLD) {
      setIndicatorKey(ind.key);
      return;
    }
    selectCountry(ind.iso3, { key: ind.key, fly: unionBbox(ind.levels.map((x) => x.layer), data.metas) });
  };
  // The Points (or Lines) switch: all points and lines of the family together. Layers of a country choose it and fly there.
  const onPoints = (row: PanelRow, on: boolean) => {
    setOverlays((prev) => ({ ...prev, ...Object.fromEntries(row.overlays.map((o) => [o.layer.layer_id, on])) }));
    const own = row.overlays.find((o) => o.iso3 !== WORLD && (country === null || o.iso3 === country)) ?? row.overlays.find((o) => o.iso3 !== WORLD);
    if (on && own && !row.overlays.some((o) => o.iso3 === WORLD)) {
      const fly = unionBbox([own.layer], data.metas);
      if (country !== own.iso3) selectCountry(own.iso3, { key: indicatorKey ?? undefined, fly });
      else if (fly) mapRef.current?.fitBounds(fly);
    }
  };
  // A family found by the search: its points if it has them, otherwise its colors
  const onFound = (row: PanelRow) => {
    if (row.overlays.length > 0) onPoints(row, true);
    else {
      const ind = colorsOf(row, country);
      if (ind && indicatorKey !== ind.key) onColors(row);
    }
  };

  const onUnit = useCallback((u: UnitRef) => {
    setUnit(u.level === 0 ? null : u);
    setCard(null);
    setNonce((n) => n + 1);
    ensureTerritory();
  }, [ensureTerritory]);

  const toWorld = useCallback(() => {
    setCountry(null);
    setUnit(null);
    setCard(null);
    setWorldOpen(true);
  }, []);
  const backToGlobe = () => {
    toWorld();
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
    if (!card || card.type === 'layer') return null;
    const layer = data.layers.find((l) => l.layer_id === card.layerId);
    if (!layer) return null;
    // several objects at one spot: the outline sits on the spot, so any of them marks it
    const props = card.type === 'record' ? card.props : card.items[0];
    const v = props?.[MODULE_BY_TYPE[layer.tiles.geometry_type].keyField];
    return v === undefined || v === null ? null : { layerId: card.layerId, key: String(v) };
  })();

  // Legend heading: indicator title and the level that is drawn
  const heading = indicator ? `${indicator.title} · ${levelWord(fill ? fill.level : selLevel, indicator, indicator.iso3, data.unit_words)} level` : null;
  const finest = indicator ? indicator.levels[indicator.levels.length - 1] : null;
  const note =
    indicator && !fill && finest
      ? `No data at this level in this release. Zoom in to see ${levelWord(finest.level, indicator, indicator.iso3, data.unit_words).toLowerCase()} data.`
      : null;
  // The legend of a family stands right under its row (SPEC_WEB_territory r9 16): in the left panel for a family
  // of the world, in the card of the country for a family of that country only
  const legendFor = (place: 'world' | 'country') => (row: PanelRow) => {
    if (place === 'country' && row.iso3 === WORLD) return null;
    const ownsFill = indicator !== null && row.fills.some((i) => i.key === indicator.key);
    const ls = [...(ownsFill && fill ? [fill.layer] : []), ...row.overlays.map((o) => o.layer).filter((l) => overlays[l.layer_id])];
    if (!ownsFill && ls.length === 0) return null;
    return (
      <div className="mx-1 mt-1 rounded-md border border-line bg-surface p-2">
        {ownsFill && heading && <p className="mb-2 text-sm font-semibold leading-tight text-ink">{heading}</p>}
        {ownsFill && note && <p className="mb-2 rounded-md border border-dashed border-[#8a8f96] p-2 text-xs text-ink2">{note}</p>}
        <Legend layers={ls} metas={data.metas} typeFilter={typeFilter} onTypeFilter={setTypeFilter} />
      </div>
    );
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1">
        <MapCanvas
          ref={mapRef}
          data={data}
          activeId={activeId}
          fillUnderSelection={fill !== null && indicator !== null && (indicator.iso3 === WORLD || indicator.iso3 === country)}
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
          onWorld={toWorld}
          onFan={(f) => setFanSpot(f && Number(f.props[data.metas[data.layers.find((l) => l.layer_id === f.layerId)?.meta_id ?? '']?.display?.count_field ?? '']) <= data.fan_max ? f : null)}
          worldOn={worldOpen && !country}
          typeFilter={typeFilter}
          onUnit={onUnit}
          onZoom={setZoom}
          onReady={onReady}
          onFailed={onFailed}
        />
        {fanSpot && card?.type === 'record' && card.layerId === fanSpot.layerId && card.props.record_id === fanSpot.props.record_id && (
          <Fan data={data} spot={fanSpot} typeFilter={typeFilter} onOpen={(layer, row) => setCard({ type: 'record', layerId: layer.layer_id, props: row })} />
        )}
        <LegendCard
          data={data}
          covered={card !== null}
          nonce={nonce}
          rows={worldRows}
          activeFill={indicator?.key ?? null}
          overlays={overlays}
          failed={failed}
          onColors={onColors}
          onPoints={onPoints}
          onInfo={(id) => setCard({ type: 'layer', layerId: id })}
          onSearch={(c) => selectCountry(c.iso3, { fly: c.bbox })}
          allRows={rows}
          legendOf={legendFor('world')}
          onFound={onFound}
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
          model={fullModel}
          hiddenIndicators={hiddenInds}
          indicator={indicator && country && (indicator.iso3 === WORLD || indicator.iso3 === country) ? indicator : null}
          unit={chosen}
          territory={territory}
          hidden={card !== null}
          nonce={nonce}
          selLevel={selLevel}
          countryRows={countryRows}
          overlays={overlays}
          failed={failed}
          onColors={onColors}
          onPoints={onPoints}
          legendOf={legendFor('country')}
          onInfo={(id) => setCard({ type: 'layer', layerId: id })}
          onWorld={backToGlobe}
          onCrumb={onCrumb}
        />
        {worldOpen && !country && <WorldCard world={fullWorld} hidden={card !== null} onClose={() => setWorldOpen(false)} />}
        <InfoCard data={data} card={card} typeFilter={typeFilter} onClose={() => setCard(null)} />
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
