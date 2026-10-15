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
import { fillLevelOf, buildCountries, levelWord, selectionLevel } from '@/lib/indicators';
import { groupByCountry, unionBbox } from '@/lib/layers';
import { levelsOfCountry, loadTerritory } from '@/lib/territory';
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
  const countries = useMemo(
    () => buildCountries(groupByCountry(layers, data.metas, data.default_layer), data.metas, (l) => MODULE_BY_TYPE[l.tiles.geometry_type].exclusive),
    [layers, data.metas, data.default_layer],
  );

  const model = countries.find((c) => c.iso3 === country) ?? null;
  const countryName = model?.name ?? (country ? countryNameFromIso3(country) : '');
  const indicator = model ? model.indicators.find((i) => i.key === indicatorKey) ?? model.indicators[0] ?? null : null;

  // Level a click selects, from the zoom; the fill is the finest layer of the indicator not finer than that
  const selLevel = selectionLevel(zoom, data.level_zoom, levelsOfCountry(territory, country ?? ''));
  const fill = indicator ? fillLevelOf(indicator, selLevel) : null;
  const activeId = fill?.layer.layer_id ?? 'none';
  const chosen: UnitRef | null = country ? unit ?? { unit_id: country, name: countryName, level: 0 } : null;

  // Points and lines of the chosen country that are switched on
  const overlaysOn = model ? model.overlays.filter((l) => overlays[l.layer_id]) : [];
  // Only the chosen country's points and lines are drawn
  const shownOverlays: Record<string, boolean> = Object.fromEntries(overlaysOn.map((l) => [l.layer_id, true]));

  const selectCountry = useCallback(
    (iso3: string) => {
      const m = countries.find((c) => c.iso3 === iso3);
      setCountry(iso3);
      setUnit(null);
      setCard(null);
      setNonce((n) => n + 1);
      // The indicator: the default one if this country has it, otherwise its first
      const byDefault = data.default_layer ? m?.indicators.find((i) => i.levels.some((x) => x.layer.layer_id === data.default_layer)) : undefined;
      setIndicatorKey((byDefault ?? m?.indicators[0])?.key ?? null);
      loadTerritory().then(setTerritory).catch(() => undefined);
      if (m) {
        const ind = byDefault ?? m.indicators[0];
        const b = ind ? unionBbox(ind.levels.map((x) => x.layer), data.metas) : null;
        if (b) mapRef.current?.fitBounds(b);
      }
    },
    [countries, data.default_layer, data.metas],
  );

  const onUnit = useCallback((u: UnitRef) => {
    setUnit(u.level === 0 ? null : u);
    setCard(null);
    setNonce((n) => n + 1);
    loadTerritory().then(setTerritory).catch(() => undefined);
  }, []);

  const toWorld = () => {
    setCountry(null);
    setUnit(null);
    setCard(null);
    setIndicatorKey(null);
    mapRef.current?.fitWorld();
  };

  // A step of the path: the country or a unit above the chosen one
  const onCrumb = (unitId: string) => {
    if (!country) return;
    if (unitId === country) {
      setUnit(null);
      const b = indicator ? unionBbox(indicator.levels.map((x) => x.layer), data.metas) : null;
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
  const heading = indicator && fill ? `${indicator.title} · ${levelWord(fill.level, indicator, indicator.iso3, data.unit_words)} level` : null;
  const legendLayers = fill ? [fill.layer, ...overlaysOn] : [];

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
          onSelect={setCard}
          onCountry={selectCountry}
          onUnit={onUnit}
          onZoom={setZoom}
          onReady={onReady}
          onFailed={onFailed}
        />
        <LegendCard data={data} heading={heading} layers={legendLayers} covered={card !== null} />
        <MapNav preview={data.channel === 'dev'} />
        <TerritoryPanel
          data={data}
          countries={countries}
          countryIso={country}
          countryName={countryName}
          model={model}
          indicator={indicator}
          overlays={overlays}
          failed={failed}
          unit={chosen}
          territory={territory}
          hidden={card !== null}
          nonce={nonce}
          selLevel={selLevel}
          onIndicator={(k) => { setIndicatorKey(k); }}
          onOverlay={(id, on) => setOverlays((prev) => ({ ...prev, [id]: on }))}
          onCountry={selectCountry}
          onWorld={toWorld}
          onCrumb={onCrumb}
          onInfo={(id) => setCard({ type: 'layer', layerId: id })}
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
