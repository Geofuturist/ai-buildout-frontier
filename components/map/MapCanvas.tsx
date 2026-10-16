'use client';

import 'maplibre-gl/dist/maplibre-gl.css';
import { Fragment, forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react';
import MapGL, { Layer, NavigationControl, Source } from 'react-map-gl/maplibre';
import type { MapLayerMouseEvent, MapRef } from 'react-map-gl/maplibre';
import type { MapGeoJSONFeature } from 'maplibre-gl';
import type { ExpressionSpecification } from 'maplibre-gl';
import { registerPmtiles } from './pmtiles';
import type { CardState, MapData, UnitRef } from './types';
import { levelNumber } from '@/lib/indicators';
import { COLORS } from '@/lib/style';
import { MODULES, MODULE_BY_TYPE } from './modules';
import { selectBoundaryLayers, selectDataLayers } from './select';

registerPmtiles();

const BEFORE = 'labels-start';
const HIT = ['adm0-hit', 'adm1-hit', 'adm2-hit'];
const STYLE_URL = process.env.NEXT_PUBLIC_BASEMAP_STYLE || '/styles/abf-base.json';

export interface MapHandle {
  fitBounds: (bbox: [number, number, number, number]) => void;
  fitWorld: () => void;
  /** Fits the view to a unit using the boundary tiles that are loaded; false if none of its geometry is loaded. */
  fitUnit: (unitId: string, level: number) => boolean;
}

interface Props {
  data: MapData;
  /** the fill layer that is drawn (only one, of the chosen country), or 'none' */
  activeId: string;
  overlays: Record<string, boolean>;
  /** the point or line record shown in the card, if any */
  selected: { layerId: string; key: string } | null;
  /** the chosen country and the level a click selects (0 country, 1 ADM1, 2 ADM2) */
  country: string | null;
  selectLevel: number;
  selectedUnit: UnitRef | null;
  /** level (0, 1, 2) at which plain polygons of the chosen country are drawn, when the indicator has no data there */
  neutralLevel: number | null;
  /** countries with data: tinted on the start globe (no country chosen) */
  dataCountries: string[];
  onSelect: (card: CardState) => void;
  onCountry: (iso3: string) => void;
  onUnit: (u: UnitRef) => void;
  onZoom: (zoom: number) => void;
  onReady?: () => void;
  onFailed: (layerId: string) => void;
}

const MapCanvas = forwardRef<MapHandle, Props>(function MapCanvas({ data, activeId, overlays, selected, country, selectLevel, selectedUnit, neutralLevel, dataCountries, onSelect, onCountry, onUnit, onZoom, onReady, onFailed }, ref) {
  const mapRef = useRef<MapRef>(null);
  const [cursor, setCursor] = useState<string>('');

  const bnd = useMemo(() => {
    const all = selectBoundaryLayers(data);
    const by = (sl: string) => all.find((l) => l.tiles.source_layer === sl);
    return { adm0: by('adm0'), adm1: by('adm1'), adm2: by('adm2'), disputed: by('disputed_unassigned') };
  }, [data]);

  const dataLayers = useMemo(() => selectDataLayers(data), [data]);

  // layer_ids that are switched on: the active exclusive layer plus the ticked overlays
  const visible = useMemo(() => {
    const v = new Set<string>();
    for (const l of dataLayers) {
      if (MODULE_BY_TYPE[l.tiles.geometry_type].exclusive ? l.layer_id === activeId : overlays[l.layer_id]) v.add(l.layer_id);
    }
    return v;
  }, [dataLayers, activeId, overlays]);

  useImperativeHandle(ref, () => ({
    fitBounds: (b) => mapRef.current?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 24, duration: 1200 }),
    fitWorld: () => mapRef.current?.easeTo({ center: [-40, 30], zoom: 1.5, duration: 1200 }),
    fitUnit: (unitId, level) => {
      const sl = [bnd.adm0, bnd.adm1, bnd.adm2][level]?.tiles.source_layer;
      const map = mapRef.current?.getMap();
      if (!map || !sl) return false;
      const feats = map.querySourceFeatures('boundaries', { sourceLayer: sl, filter: ['==', ['get', 'unit_id'], unitId] });
      let b: number[] | null = null;
      const walk = (c: unknown) => {
        if (Array.isArray(c) && typeof c[0] === 'number') {
          const [x, y] = c as number[];
          b = b ? [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)] : [x, y, x, y];
        } else if (Array.isArray(c)) c.forEach(walk);
      };
      for (const f of feats) walk((f.geometry as { coordinates?: unknown }).coordinates);
      if (!b) return false;
      const bb = b as number[];
      mapRef.current?.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], { padding: 40, duration: 1200 });
      return true;
    },
  }));

  // Clickable: overlay objects (points, lines) of the switched-on layers, then the invisible boundary fills of the
  // levels that exist. Polygon fills are not clickable themselves: a click chooses a unit of the selection level.
  const interactiveLayerIds = useMemo(
    () => [
      ...dataLayers.filter((l) => visible.has(l.layer_id) && !MODULE_BY_TYPE[l.tiles.geometry_type].exclusive).flatMap((l) => MODULE_BY_TYPE[l.tiles.geometry_type].hitLayerIds(l.layer_id)),
      ...(bnd.adm2 ? [HIT[2]] : []),
      ...(bnd.adm1 ? [HIT[1]] : []),
      ...(bnd.adm0 ? [HIT[0]] : []),
    ],
    [dataLayers, visible, bnd.adm0, bnd.adm1, bnd.adm2],
  );

  // What is under the pointer: an object of a switched-on overlay, a country, or a unit of the selection level
  type Target = { kind: 'record'; f: MapGeoJSONFeature } | { kind: 'country'; iso3: string; unit: UnitRef } | { kind: 'unit'; unit: UnitRef } | null;
  const targetOf = useCallback(
    (all: MapGeoJSONFeature[]): Target => {
      const over = all.find((x) => x.source !== 'boundaries');
      if (over) return { kind: 'record', f: over };
      const hits = all.filter((x) => x.source === 'boundaries' && typeof x.properties?.unit_id === 'string');
      if (hits.length === 0) return null; // the sea, a disputed area: nothing
      const iso3 = String(hits[0].properties?.iso3 ?? '');
      if (!iso3) return null;
      const ref = (f: MapGeoJSONFeature): UnitRef => ({ unit_id: String(f.properties?.unit_id), name: String(f.properties?.name ?? ''), level: levelNumber(String(f.properties?.level)) });
      const adm0 = hits.find((x) => x.properties?.iso3 === iso3 && levelNumber(String(x.properties?.level)) === 0) ?? hits[0];
      // A click in another country chooses that country; inside the chosen country it chooses a unit of the selection level
      if (iso3 !== country) return { kind: 'country', iso3, unit: ref(adm0) };
      const inCountry = hits.filter((x) => x.properties?.iso3 === iso3);
      const ok = inCountry.filter((x) => levelNumber(String(x.properties?.level)) <= selectLevel);
      const pick = ok.sort((a, b) => levelNumber(String(b.properties?.level)) - levelNumber(String(a.properties?.level)))[0] ?? inCountry[0];
      return { kind: 'unit', unit: ref(pick) };
    },
    [country, selectLevel],
  );

  const [hover, setHover] = useState<UnitRef | null>(null);
  const onMove = useCallback(
    (e: MapLayerMouseEvent) => {
      const t = targetOf(e.features ?? []);
      setCursor(t ? 'pointer' : '');
      const u = t && t.kind !== 'record' ? t.unit : null;
      setHover((prev) => (prev?.unit_id === u?.unit_id && prev?.level === u?.level ? prev : u));
    },
    [targetOf],
  );

  const onClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const t = targetOf(e.features ?? []);
      if (!t) return;
      if (t.kind === 'record') onSelect({ type: 'record', layerId: t.f.source, props: { ...(t.f.properties as Record<string, unknown>) } });
      else if (t.kind === 'country') onCountry(t.iso3);
      else onUnit(t.unit);
    },
    [targetOf, onSelect, onCountry, onUnit],
  );

  const layerIdSet = useMemo(() => new Set(data.layers.map((l) => l.layer_id)), [data]);
  const ctx = useMemo(() => ({ metas: data.metas, visible, selected, before: BEFORE }), [data.metas, visible, selected]);

  return (
    <MapGL
      ref={mapRef}
      initialViewState={{ longitude: -40, latitude: 30, zoom: 1.5 }}
      projection="globe"
      mapStyle={STYLE_URL}
      style={{ width: '100%', height: '100%' }}
      attributionControl={false}
      interactiveLayerIds={interactiveLayerIds}
      cursor={cursor}
      onMouseMove={onMove}
      onMouseLeave={() => { setCursor(''); setHover(null); }}
      onClick={onClick}
      onLoad={() => {
        // Test hook, only in a build made with NEXT_PUBLIC_E2E=1 (never set on Vercel)
        if (process.env.NEXT_PUBLIC_E2E) (window as unknown as { __map?: unknown }).__map = mapRef.current?.getMap();
        onReady?.();
      }}
      onMove={(e) => onZoom(Math.round(e.viewState.zoom * 10) / 10)}
      onError={(e) => {
        const sid = (e as unknown as { sourceId?: string }).sourceId;
        if (sid && layerIdSet.has(sid)) onFailed(sid);
      }}
    >
      <NavigationControl position="bottom-right" showCompass={false} />

      {/* 1. Fill layers: all mounted in a fixed order, only the active one is visible */}
      {MODULES.filter((m) => m.exclusive).map((m) => (
        <Fragment key={m.type}>{m.renderLayers(dataLayers.filter((l) => l.tiles.geometry_type === m.type), ctx)}</Fragment>
      ))}

      {/* 2. Boundaries: one PMTiles file, several source layers */}
      {bnd.adm0 && (
        <Source id="boundaries" type="vector" url={`pmtiles://${bnd.adm0.tiles.url}`}>
          {/* Start globe: countries with data in a grey tint (flat list: <Source> passes its id to direct children only) */}
          <Layer
            id="data-countries"
            type="fill"
            source-layer={bnd.adm0.tiles.source_layer}
            beforeId={BEFORE}
            filter={['in', ['get', 'iso3'], ['literal', dataCountries]] as ExpressionSpecification}
            layout={{ visibility: country ? 'none' : 'visible' }}
            paint={{ 'fill-color': COLORS.dataCountry, 'fill-opacity': 0.5 }}
          />
          {/* Plain polygons of the level the map shows when the indicator has no data at that level */}
          {[bnd.adm0, bnd.adm1, bnd.adm2].flatMap((b, i) =>
            b
              ? [
                  <Layer
                    key={`neutral-${i}`}
                    id={`neutral-${i}`}
                    type="fill"
                    source-layer={b.tiles.source_layer}
                    beforeId={BEFORE}
                    filter={['==', ['get', 'iso3'], country ?? ''] as ExpressionSpecification}
                    layout={{ visibility: country && neutralLevel === i ? 'visible' : 'none' }}
                    paint={{ 'fill-color': COLORS.neutralUnit }}
                  />,
                ]
              : [],
          )}
          {bnd.disputed && (
            <Layer
              id="disputed-fill"
              type="fill"
              source-layer={bnd.disputed.tiles.source_layer}
              beforeId={BEFORE}
              paint={{ 'fill-color': COLORS.disputedFill }}
            />
          )}
          {bnd.disputed && (
            <Layer
              id="disputed-line"
              type="line"
              source-layer={bnd.disputed.tiles.source_layer}
              beforeId={BEFORE}
              paint={{ 'line-color': COLORS.disputedLine, 'line-width': 0.8, 'line-dasharray': [2, 2] }}
            />
          )}
          {bnd.disputed && (
            <Layer
              id="disputed-label"
              type="symbol"
              source-layer={bnd.disputed.tiles.source_layer}
              beforeId={BEFORE}
              minzoom={3}
              layout={{
                'text-field': ['concat', ['coalesce', ['get', 'label'], 'Disputed area'], '\n', 'Not assigned to any country'] as ExpressionSpecification,
                'text-font': ['Noto Sans Regular'],
                'text-size': 10,
                'text-max-width': 8,
              }}
              paint={{ 'text-color': '#52514e', 'text-halo-color': COLORS.surface, 'text-halo-width': 1.2 }}
            />
          )}
          {bnd.adm2 && (
            <Layer
              id="adm2-lines"
              type="line"
              source-layer={bnd.adm2.tiles.source_layer}
              beforeId={BEFORE}
              minzoom={5}
              paint={{ 'line-color': COLORS.surface, 'line-width': 0.4 }}
            />
          )}
          {bnd.adm1 && (
            <Layer
              id="adm1-lines"
              type="line"
              source-layer={bnd.adm1.tiles.source_layer}
              beforeId={BEFORE}
              minzoom={3}
              paint={{ 'line-color': COLORS.adm1, 'line-width': 0.8 }}
            />
          )}
          {/* Invisible: nothing is recoloured; these only let a click choose a country or a unit */}
          {([bnd.adm0, bnd.adm1, bnd.adm2] as (typeof bnd.adm0)[]).map(
            (b, i) =>
              b && (
                <Layer key={HIT[i]} id={HIT[i]} type="fill" source-layer={b.tiles.source_layer} beforeId={BEFORE} paint={{ 'fill-opacity': 0 }} />
              ),
          )}
          <Layer
            id="adm0-lines"
            type="line"
            source-layer={bnd.adm0.tiles.source_layer}
            beforeId={BEFORE}
            paint={{ 'line-color': COLORS.adm0, 'line-width': 1 }}
          />
          {/* Hover: grey outline of the country or unit a click would choose now (its own style, not the teal of the choice) */}
          {[bnd.adm0, bnd.adm1, bnd.adm2].flatMap((b, i) =>
            b
              ? [
                  <Layer
                    key={`hov-line-${i}`}
                    id={`hov-line-${i}`}
                    type="line"
                    source-layer={b.tiles.source_layer}
                    beforeId={BEFORE}
                    filter={['==', ['get', 'unit_id'], hover && hover.level === i ? hover.unit_id : ''] as ExpressionSpecification}
                    paint={{ 'line-color': COLORS.hover, 'line-width': 1.8, 'line-dasharray': [3, 1.5] }}
                  />,
                ]
              : [],
          )}
          {/* The chosen unit: teal outline on a light underlay, in the layer of its own level.
              (Flat list on purpose: <Source> passes its id only to direct children, not through fragments.) */}
          {[bnd.adm0, bnd.adm1, bnd.adm2].flatMap((b, i) =>
            b
              ? [
                  <Layer
                    key={`sel-under-${i}`}
                    id={`sel-under-${i}`}
                    type="line"
                    source-layer={b.tiles.source_layer}
                    beforeId={BEFORE}
                    filter={['==', ['get', 'unit_id'], selectedUnit && selectedUnit.level === i ? selectedUnit.unit_id : ''] as ExpressionSpecification}
                    paint={{ 'line-color': COLORS.surface, 'line-width': 5 }}
                  />,
                  <Layer
                    key={`sel-line-${i}`}
                    id={`sel-line-${i}`}
                    type="line"
                    source-layer={b.tiles.source_layer}
                    beforeId={BEFORE}
                    filter={['==', ['get', 'unit_id'], selectedUnit && selectedUnit.level === i ? selectedUnit.unit_id : ''] as ExpressionSpecification}
                    paint={{ 'line-color': COLORS.selected, 'line-width': 2.5 }}
                  />,
                ]
              : [],
          )}
        </Source>
      )}

      {/* 3. Overlays: lines, then points (each geometry type has its own module) */}
      {MODULES.filter((m) => !m.exclusive).map((m) => (
        <Fragment key={m.type}>{m.renderLayers(dataLayers.filter((l) => l.tiles.geometry_type === m.type), ctx)}</Fragment>
      ))}
    </MapGL>
  );
});

export default MapCanvas;
