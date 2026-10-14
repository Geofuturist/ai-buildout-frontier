'use client';

import 'maplibre-gl/dist/maplibre-gl.css';
import { Fragment, forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react';
import MapGL, { Layer, NavigationControl, Source } from 'react-map-gl/maplibre';
import type { MapLayerMouseEvent, MapRef } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import { registerPmtiles } from './pmtiles';
import type { CardState, MapData } from './types';
import { COLORS } from '@/lib/style';
import { MODULES, MODULE_BY_TYPE } from './modules';
import { selectBoundaryLayers, selectDataLayers } from './select';

registerPmtiles();

const BEFORE = 'labels-start';
const COUNTRY_HIT = 'adm0-hit';
const STYLE_URL = process.env.NEXT_PUBLIC_BASEMAP_STYLE || '/styles/abf-base.json';

export interface MapHandle {
  fitBounds: (bbox: [number, number, number, number]) => void;
  fitWorld: () => void;
}

interface Props {
  data: MapData;
  activeId: string;
  overlays: Record<string, boolean>;
  selected: { layerId: string; key: string } | null;
  onSelect: (card: CardState) => void;
  onCountry: (iso3: string) => void;
  onFailed: (layerId: string) => void;
}

const MapCanvas = forwardRef<MapHandle, Props>(function MapCanvas({ data, activeId, overlays, selected, onSelect, onCountry, onFailed }, ref) {
  const mapRef = useRef<MapRef>(null);
  const [cursor, setCursor] = useState<string>('');

  useImperativeHandle(ref, () => ({
    fitBounds: (b) => mapRef.current?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 24, duration: 1200 }),
    fitWorld: () => mapRef.current?.easeTo({ center: [-40, 30], zoom: 1.5, duration: 1200 }),
  }));

  const dataLayers = useMemo(() => selectDataLayers(data), [data]);

  // layer_ids that are switched on: the active exclusive layer plus the ticked overlays
  const visible = useMemo(() => {
    const v = new Set<string>();
    for (const l of dataLayers) {
      if (MODULE_BY_TYPE[l.tiles.geometry_type].exclusive ? l.layer_id === activeId : overlays[l.layer_id]) v.add(l.layer_id);
    }
    return v;
  }, [dataLayers, activeId, overlays]);

  const bnd = useMemo(() => {
    const all = selectBoundaryLayers(data);
    const by = (sl: string) => all.find((l) => l.tiles.source_layer === sl);
    return { adm0: by('adm0'), adm1: by('adm1'), adm2: by('adm2'), disputed: by('disputed_unassigned') };
  }, [data]);

  // Data layers first; the invisible country fill is last and only catches clicks that miss every object
  const interactiveLayerIds = useMemo(
    () => [
      ...dataLayers.filter((l) => visible.has(l.layer_id)).flatMap((l) => MODULE_BY_TYPE[l.tiles.geometry_type].hitLayerIds(l.layer_id)),
      ...(bnd.adm0 ? [COUNTRY_HIT] : []),
    ],
    [dataLayers, visible, bnd.adm0],
  );

  const onClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const all = e.features ?? [];
      // An object of a switched-on layer wins over the country under it
      const f = all.find((x) => x.layer.id !== COUNTRY_HIT);
      if (f) {
        // every layer has its own source, and the source id is the layer_id
        onSelect({ type: 'record', layerId: f.source, props: { ...(f.properties as Record<string, unknown>) } });
        return;
      }
      const iso3 = all[0]?.properties?.iso3;
      if (typeof iso3 === 'string' && iso3) onCountry(iso3);
      else onSelect(null);
    },
    [onSelect, onCountry],
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
      onMouseEnter={() => setCursor('pointer')}
      onMouseLeave={() => setCursor('')}
      onClick={onClick}
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
          {/* Invisible: nothing is recoloured; it only lets a click choose a country (ARCH 14.10, package 1c) */}
          <Layer
            id={COUNTRY_HIT}
            type="fill"
            source-layer={bnd.adm0.tiles.source_layer}
            beforeId={BEFORE}
            paint={{ 'fill-opacity': 0 }}
          />
          <Layer
            id="adm0-lines"
            type="line"
            source-layer={bnd.adm0.tiles.source_layer}
            beforeId={BEFORE}
            paint={{ 'line-color': COLORS.adm0, 'line-width': 1 }}
          />
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
