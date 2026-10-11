'use client';

import 'maplibre-gl/dist/maplibre-gl.css';
import { forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react';
import MapGL, { Layer, NavigationControl, Source } from 'react-map-gl/maplibre';
import type { MapLayerMouseEvent, MapRef } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import { registerPmtiles } from './pmtiles';
import type { CardState, MapData } from './types';
import { COLORS, bandColorExpression, bandWidthExpression, fillColorExpression } from '@/lib/style';
import type { LayerEntry } from '@/lib/data';

registerPmtiles();

const BEFORE = 'labels-start';
const STYLE_URL = process.env.NEXT_PUBLIC_BASEMAP_STYLE || '/styles/abf-base.json';
const HIT_SUFFIXES = ['-fill', '-nc-hit'];

export interface MapHandle {
  fitUS: () => void;
  fitWorld: () => void;
}

interface Props {
  data: MapData;
  activeId: string;
  linesOn: Record<string, boolean>;
  selectedUnit: string | null;
  onSelect: (card: CardState) => void;
  onFailed: (layerId: string) => void;
}

const COVERED = ['==', ['get', 'coverage_status'], 'covered'] as ExpressionSpecification;
const NOT_COVERED = ['!=', ['get', 'coverage_status'], 'covered'] as ExpressionSpecification;

const MapCanvas = forwardRef<MapHandle, Props>(function MapCanvas(
  { data, activeId, linesOn, selectedUnit, onSelect, onFailed },
  ref,
) {
  const mapRef = useRef<MapRef>(null);
  const [cursor, setCursor] = useState<string>('');

  useImperativeHandle(ref, () => ({
    fitUS: () => mapRef.current?.fitBounds([[-125.5, 24], [-66, 49.8]], { padding: 24, duration: 1200 }),
    fitWorld: () => mapRef.current?.easeTo({ center: [-40, 30], zoom: 1.5, duration: 1200 }),
  }));

  const polygons = useMemo(
    () =>
      data.layers.filter(
        (l) => l.dataset === 'abf-layers' && l.tiles.geometry_type === 'polygon' && data.metas[l.meta_id]?.display?.value_field,
      ),
    [data],
  );
  const lines = useMemo(
    () => data.layers.filter((l) => l.dataset === 'abf-layers' && l.tiles.geometry_type === 'line'),
    [data],
  );
  const bnd = useMemo(() => {
    const all = data.layers.filter((l) => l.dataset === 'abf-boundaries');
    const by = (sl: string) => all.find((l) => l.tiles.source_layer === sl);
    return { adm0: by('adm0'), adm1: by('adm1'), adm2: by('adm2'), disputed: by('disputed_unassigned') };
  }, [data]);

  const interactiveLayerIds = useMemo(() => {
    const ids: string[] = [];
    for (const l of lines) if (linesOn[l.layer_id]) ids.push(`${l.layer_id}-hit`);
    if (activeId !== 'none') for (const s of HIT_SUFFIXES) ids.push(`${activeId}${s}`);
    return ids;
  }, [activeId, lines, linesOn]);

  const onClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const f = e.features && e.features[0];
      if (!f) {
        onSelect(null);
        return;
      }
      const lid = f.layer.id;
      let layerId = lid;
      if (lid.endsWith('-hit') && !lid.endsWith('-nc-hit')) layerId = lid.slice(0, -4);
      else {
        const suffix = HIT_SUFFIXES.find((s) => lid.endsWith(s));
        if (suffix) layerId = lid.slice(0, -suffix.length);
      }
      onSelect({ type: 'record', layerId, props: { ...(f.properties as Record<string, unknown>) } });
    },
    [onSelect],
  );

  const layerIdSet = useMemo(() => new Set(data.layers.map((l) => l.layer_id)), [data]);

  const lineLayer = (l: LayerEntry) => {
    const visibility = linesOn[l.layer_id] ? 'visible' : 'none';
    return (
      <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
        <Layer
          id={`${l.layer_id}-line`}
          type="line"
          source-layer={l.tiles.source_layer}
          beforeId={BEFORE}
          filter={['!=', ['get', 'voltage_band'], 'unknown'] as ExpressionSpecification}
          layout={{ visibility, 'line-cap': 'round' }}
          paint={{ 'line-color': bandColorExpression(), 'line-width': bandWidthExpression() }}
        />
        <Layer
          id={`${l.layer_id}-line-unknown`}
          type="line"
          source-layer={l.tiles.source_layer}
          beforeId={BEFORE}
          filter={['==', ['get', 'voltage_band'], 'unknown'] as ExpressionSpecification}
          layout={{ visibility }}
          paint={{ 'line-color': '#8a8f96', 'line-width': 0.8, 'line-dasharray': [2, 2] }}
        />
        <Layer
          id={`${l.layer_id}-hit`}
          type="line"
          source-layer={l.tiles.source_layer}
          beforeId={BEFORE}
          layout={{ visibility }}
          paint={{ 'line-color': '#ffffff', 'line-opacity': 0.01, 'line-width': 12 }}
        />
      </Source>
    );
  };

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

      {/* 1. County layers: all mounted in a fixed order, only the active one is visible */}
      {polygons.map((l) => {
        const meta = data.metas[l.meta_id];
        const d = meta.display!;
        const field = d.value_field!;
        const vis = l.layer_id === activeId ? 'visible' : 'none';
        return (
          <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
            <Layer
              id={`${l.layer_id}-fill`}
              type="fill"
              source-layer={l.tiles.source_layer}
              beforeId={BEFORE}
              filter={COVERED}
              layout={{ visibility: vis }}
              paint={{ 'fill-color': fillColorExpression(field, d.breaks ?? []) }}
            />
            {d.zero_class && (
              <Layer
                id={`${l.layer_id}-zero`}
                type="line"
                source-layer={l.tiles.source_layer}
                beforeId={BEFORE}
                filter={['all', COVERED, ['==', ['get', field], 0]] as ExpressionSpecification}
                layout={{ visibility: vis }}
                paint={{ 'line-color': COLORS.zeroStroke, 'line-width': 0.5 }}
              />
            )}
            {/* Not covered: no fill, dashed outline (fallback approved in SPEC_WEB section 6) */}
            <Layer
              id={`${l.layer_id}-nc`}
              type="line"
              source-layer={l.tiles.source_layer}
              beforeId={BEFORE}
              filter={NOT_COVERED}
              layout={{ visibility: vis }}
              paint={{ 'line-color': COLORS.notCovered, 'line-width': 0.8, 'line-dasharray': [2, 2] }}
            />
            <Layer
              id={`${l.layer_id}-nc-hit`}
              type="fill"
              source-layer={l.tiles.source_layer}
              beforeId={BEFORE}
              filter={NOT_COVERED}
              layout={{ visibility: vis }}
              paint={{ 'fill-color': COLORS.surface, 'fill-opacity': 0.01 }}
            />
            <Layer
              id={`${l.layer_id}-sel`}
              type="line"
              source-layer={l.tiles.source_layer}
              beforeId={BEFORE}
              filter={['==', ['get', 'unit_id'], selectedUnit ?? ''] as ExpressionSpecification}
              layout={{ visibility: vis === 'visible' && selectedUnit ? 'visible' : 'none' }}
              paint={{ 'line-color': COLORS.selected, 'line-width': 2.5 }}
            />
          </Source>
        );
      })}

      {/* 2. Boundaries: one PMTiles file, several source layers */}
      {bnd.adm0 && (
        <Source id="abf-boundaries" type="vector" url={`pmtiles://${bnd.adm0.tiles.url}`}>
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
          <Layer
            id="adm0-lines"
            type="line"
            source-layer={bnd.adm0.tiles.source_layer}
            beforeId={BEFORE}
            paint={{ 'line-color': COLORS.adm0, 'line-width': 1 }}
          />
        </Source>
      )}

      {/* 3. Line overlays (transmission segments) */}
      {lines.map(lineLayer)}
    </MapGL>
  );
});

export default MapCanvas;
