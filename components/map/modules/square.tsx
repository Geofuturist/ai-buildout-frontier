'use client';

// Squares (display.symbol = "square", SPEC_GEM_plants r7 W7): one symbol layer with an SDF icon, so the fill takes the
// colour of the type. Filled square = position at the site; frame only = approximate position (coord_precision, as
// for the dots). Size by class, colour by type (display.color_field), min zoom per class is in the tiles
// (tippecanoe.minzoom), the filters by field value come from display.filters. Nothing is counted here.
import { useEffect } from 'react';
import { Layer, Source, useMap } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import type { LayerEntry, Meta } from '@/lib/data';
import { effectiveFilters, filterExpression, filtersOf, typeFilterOf } from '@/lib/filters';
import type { LayerFilters } from '@/lib/filters';
import { COLORS } from '@/lib/style';
import { SIZE_RADII, classColor, isTyped, sizeLabels, typeColorExpression } from '@/lib/pointSize';
import type { Typed } from '@/lib/pointSize';
import type { ModuleCtx } from './types';

type Display = NonNullable<Meta['display']>;

const SITE_LEVEL = 'site';
const PRECISION_FIELD = 'coord_precision';
const ICON_FILLED = 'abf-square';
const ICON_FRAME = 'abf-square-frame';
/** device px of the icon canvas, of the half side of the square and of the frame width; SDF radius as in MapLibre */
const CANVAS = 40;
const HALF = 12;
const FRAME = 5;
const SDF_RADIUS = 8;
const PIXEL_RATIO = 2;
/** side of the square at icon-size 1, in css px */
const SIDE = (2 * HALF) / PIXEL_RATIO;

export function isSquare(d: Display | undefined): boolean {
  return d?.symbol === 'square';
}

/** Size classes in order: display.size_classes, otherwise the order of the legend labels. null: a numeric size field. */
export function sizeClassesOf(d: Display): string[] | null {
  if (d.size_classes && d.size_classes.length > 0) return d.size_classes;
  if (d.legend_size_labels) {
    const keys = Object.keys(d.legend_size_labels);
    if (keys.length > 0) return keys;
  }
  return null;
}

/** Half side in px of the square by class (the radii of the dots, as sizes). */
export function halfSideExpression(d: Display): ExpressionSpecification {
  const field = d.size_field ?? '';
  const classes = sizeClassesOf(d);
  let by: unknown;
  if (classes) {
    const m: unknown[] = ['match', ['get', field]];
    classes.forEach((c, i) => m.push(c, SIZE_RADII[Math.min(i, SIZE_RADII.length - 1)]));
    m.push(SIZE_RADII[0]);
    by = m;
  } else {
    const s: unknown[] = ['step', ['to-number', ['get', field], 0], SIZE_RADII[0]];
    (d.size_breaks ?? []).forEach((b, i) => s.push(b, SIZE_RADII[Math.min(i + 1, SIZE_RADII.length - 1)]));
    by = s;
  }
  return by as ExpressionSpecification;
}

/** Signed-distance picture of a square (frame = true: a ring), encoded as MapLibre reads an SDF icon. */
export function squareSdf(frame: boolean): Uint8Array {
  const data = new Uint8Array(CANVAS * CANVAS * 4);
  for (let y = 0; y < CANVAS; y++) {
    for (let x = 0; x < CANVAS; x++) {
      const dx = Math.abs(x + 0.5 - CANVAS / 2);
      const dy = Math.abs(y + 0.5 - CANVAS / 2);
      const outer = Math.max(dx, dy) - HALF;
      const d = frame ? Math.max(outer, -outer - FRAME) : outer;
      const a = Math.max(0, Math.min(255, Math.round(255 * (0.75 - d / SDF_RADIUS))));
      const i = (y * CANVAS + x) * 4;
      data[i] = 0; data[i + 1] = 0; data[i + 2] = 0; data[i + 3] = a;
    }
  }
  return data;
}

/** Puts the two icons on the map; also when the style is loaded again (styleimagemissing). */
export function SquareIcons() {
  const { current: ref } = useMap();
  useEffect(() => {
    const map = ref?.getMap();
    if (!map) return;
    const add = (name: string) => {
      if (map.hasImage(name)) return;
      map.addImage(name, { width: CANVAS, height: CANVAS, data: squareSdf(name === ICON_FRAME) }, { sdf: true, pixelRatio: PIXEL_RATIO });
    };
    const ensure = () => { add(ICON_FILLED); add(ICON_FRAME); };
    const onMissing = (e: { id: string }) => { if (e.id === ICON_FILLED || e.id === ICON_FRAME) ensure(); };
    ensure();
    map.on('styleimagemissing', onMissing);
    return () => { map.off('styleimagemissing', onMissing); };
  }, [ref]);
  return null;
}

export function renderSquare(l: LayerEntry, d: Display, ctx: ModuleCtx) {
  const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
  const sl = l.tiles.source_layer;
  const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
  const half = halfSideExpression(d);
  const typed = isTyped(d);
  const color = typed ? typeColorExpression(d as Typed, 'fill') : (COLORS.point as unknown as ExpressionSpecification);
  const filter = filterExpression(d, ctx.layerFilters[l.layer_id]);
  const fl = filter ? { filter } : {};
  const selFilter = ['==', ['get', 'record_id'], sel ?? ''] as ExpressionSpecification;
  const selVis = visibility === 'visible' && sel ? 'visible' : 'none';
  const around = ['+', half, 4] as unknown as ExpressionSpecification;
  return (
    <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
      <Layer
        id={`${l.layer_id}-pt`}
        type="symbol"
        source-layer={sl}
        beforeId={ctx.before}
        {...fl}
        layout={{
          visibility,
          'icon-image': ['case', ['==', ['get', PRECISION_FIELD], SITE_LEVEL], ICON_FILLED, ICON_FRAME] as unknown as ExpressionSpecification,
          'icon-size': ['/', ['*', half, 2], SIDE] as unknown as ExpressionSpecification,
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          // larger squares first, so that small ones stay on top of them
          'symbol-sort-key': ['-', 0, half] as unknown as ExpressionSpecification,
        }}
        paint={{ 'icon-color': color, 'icon-opacity': 0.9, 'icon-halo-color': COLORS.surface, 'icon-halo-width': 1 }}
      />
      <Layer id={`${l.layer_id}-hit`} type="circle" source-layer={sl} beforeId={ctx.before} {...fl} layout={{ visibility }} paint={{ 'circle-radius': ['max', 9, ['+', half, 3]] as unknown as ExpressionSpecification, 'circle-color': '#ffffff', 'circle-opacity': 0.01 }} />
      <Layer id={`${l.layer_id}-sel-under`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': around, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.surface, 'circle-stroke-width': 5.5 }} />
      <Layer id={`${l.layer_id}-sel`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': around, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.selected, 'circle-stroke-width': 2.5 }} />
    </Source>
  );
}

function Sq({ side, color, frame }: { side: number; color: string; frame?: boolean }) {
  const c = 14;
  const h = side / 2;
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden className="shrink-0">
      <rect x={c - h - 1} y={c - h - 1} width={side + 2} height={side + 2} fill={COLORS.surface} fillOpacity="0.9" />
      {frame ? (
        <rect x={c - h + 1} y={c - h + 1} width={side - 2} height={side - 2} fill="none" stroke={color} strokeWidth="2" />
      ) : (
        <rect x={c - h} y={c - h} width={side} height={side} fill={color} fillOpacity="0.9" />
      )}
    </svg>
  );
}

/** One line of a filter: a tick box with the label (and the colour of a type). */
function Tick({ on, label, color, onClick, disabled }: { on: boolean; label: string; color?: string; onClick: () => void; disabled?: boolean }) {
  return (
    <li>
      <button
        type="button"
        role="checkbox"
        aria-checked={on}
        disabled={disabled}
        className={`flex min-h-[32px] w-full items-center gap-2 rounded px-1 text-left hover:bg-[#eef3f3] ${on ? 'font-semibold' : ''}`}
        onClick={onClick}
      >
        <span aria-hidden className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border ${on ? 'border-[#0f6e6e]' : 'border-[#8a8f96]'}`}>
          {on && <span className="h-2 w-2 rounded-[1px] bg-[#0f6e6e]" />}
        </span>
        {color && <span aria-hidden className="h-3 w-3 shrink-0 border border-black/20" style={{ background: color }} />}
        <span>{label}</span>
      </button>
    </li>
  );
}

/** A filter: "All" and the values; several may be ticked; nothing ticked is "All". */
function FilterList({ layerId, f, chosen, colors, onLayerFilter }: { layerId: string; f: NonNullable<ReturnType<typeof typeFilterOf>>; chosen: string[]; colors?: Record<string, string>; onLayerFilter?: (layerId: string, field: string, values: string[]) => void }) {
  const set = (v: string[]) => onLayerFilter?.(layerId, f.field, v);
  return (
    <ul className="space-y-0" role="group" aria-label={f.title}>
      <Tick on={chosen.length === 0} label="All" disabled={!onLayerFilter} onClick={() => set([])} />
      {f.values.map((v) => (
        <Tick key={v.value} on={chosen.includes(v.value)} label={v.label} color={colors?.[v.value]} disabled={!onLayerFilter} onClick={() => set(chosen.includes(v.value) ? chosen.filter((x) => x !== v.value) : [...chosen, v.value])} />
      ))}
    </ul>
  );
}

/** Legend of a square layer: the types (a filter), size classes, the frame, then the other filters. */
export function SquareLegend({ layer, d, layerFilters, onLayerFilter }: { layer: LayerEntry; d: Display; layerFilters?: LayerFilters; onLayerFilter?: (layerId: string, field: string, values: string[]) => void }) {
  const typed = isTyped(d) ? (d as Typed) : null;
  const typeFilter = typeFilterOf(d);
  const classes = sizeClassesOf(d);
  const breaks = d.size_breaks ?? [];
  const sizeText: string[] = classes
    ? classes.map((c, i) => d.legend_size_labels?.[c] ?? sizeLabels(breaks, 'MW')[i] ?? c)
    : breaks.length ? sizeLabels(breaks, 'MW') : [];
  const chosen = effectiveFilters(d, layerFilters?.[layer.layer_id]);
  const typeColors = typed ? Object.fromEntries(typed.color_classes.map((c, i) => [c, classColor(typed, c, i).fill])) : undefined;
  return (
    <div className="mt-3 first:mt-0">
      <h3 className="mb-1 text-[13px] font-semibold text-ink">{d.legend_title ?? layer.title}</h3>
      {d.legend_note && <p className="mb-1 text-xs text-muted">{d.legend_note}</p>}
      {typeFilter && <FilterList layerId={layer.layer_id} f={typeFilter} chosen={chosen[typeFilter.field] ?? []} colors={typeColors} onLayerFilter={onLayerFilter} />}
      {sizeText.length > 0 && (
        <ul className="mt-1 space-y-0 border-t border-line pt-1">
          {sizeText.map((t, i) => (
            <li key={t} className="flex items-center gap-2">
              <Sq side={SIZE_RADII[Math.min(i, SIZE_RADII.length - 1)] * 2} color="#6b6f76" />
              <span>{t}</span>
            </li>
          ))}
        </ul>
      )}
      {d.legend_approximate && (
        <ul className="mt-1 space-y-0 border-t border-line pt-1">
          <li className="flex items-center gap-2"><Sq side={10} color="#6b6f76" frame /><span>{d.legend_approximate}</span></li>
        </ul>
      )}
      {filtersOf(d).filter((f) => f.field !== typeFilter?.field).map((f) => (
        <fieldset key={f.field} className="mt-2 border-t border-line pt-2">
          {f.title && <legend className="mb-1 text-[13px] font-semibold text-ink">{f.title}</legend>}
          {f.note && <p className="mb-1 text-xs text-muted">{f.note}</p>}
          <FilterList layerId={layer.layer_id} f={f} chosen={chosen[f.field] ?? []} onLayerFilter={onLayerFilter} />
        </fieldset>
      ))}
    </div>
  );
}
