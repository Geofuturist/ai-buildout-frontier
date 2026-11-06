'use client';

// Point layers drawn as icons (SPEC_WEB_territory r11 par. 18): the shape comes from the domain (display.shape), the kind
// of status from the fields of the object (display.status_style), the colour from the type (display.color_field) or the
// layer, the size from the class (display.size_field). One symbol layer per layer; the images are drawn when the map asks
// for them (lib/icons.ts). Filters by field value (display.filters) and the filter by type work as before. Nothing is
// counted here: every number comes from the tiles.
import { useEffect } from 'react';
import { Layer, Source, useMap } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import type { LayerEntry, Meta } from '@/lib/data';
import { DRAWN, ICON_PX, ICON_RATIO, drawIcon, iconId, parseIconId } from '@/lib/icons';
import type { Kind, Shape } from '@/lib/icons';
import { effectiveFilters, filterExpression, filtersOf, typeFilterOf } from '@/lib/filters';
import type { LayerFilters } from '@/lib/filters';
import { fineCondition, kindExpression, shapeOf } from '@/lib/pointStatus';
import { COLORS } from '@/lib/style';
import {
  BADGE_COLOR, BADGE_RADIUS, SIZE_RADII, UNKNOWN_COLOR, badgeCondition, classColor, colorOf, filterColumn, groupShown, isCounted, isTyped, placeRadius, radiusExpression, sizeLabels, typeColorExpression, unknownCondition, zeroCondition,
} from '@/lib/pointSize';
import type { Counted, Typed } from '@/lib/pointSize';
import type { ModuleCtx } from './types';

type Display = NonNullable<Meta['display']>;
const num = (e: ExpressionSpecification, k: number) => ['+', e, k] as unknown as ExpressionSpecification;
const x = (e: unknown) => e as ExpressionSpecification;

/** Draws the icon the map asks for ("styleimagemissing"): the id holds shape, kind and colour. */
export function PointIcons() {
  const { current: ref } = useMap();
  useEffect(() => {
    const map = ref?.getMap();
    if (!map) return;
    const onMissing = (e: { id: string }) => {
      const p = parseIconId(e.id);
      if (!p || map.hasImage(e.id)) return;
      const canvas = document.createElement('canvas');
      canvas.width = ICON_PX;
      canvas.height = ICON_PX;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      drawIcon(ctx, p.shape, p.kind, p.color);
      const img = ctx.getImageData(0, 0, ICON_PX, ICON_PX);
      map.addImage(e.id, { width: ICON_PX, height: ICON_PX, data: new Uint8Array(img.data.buffer) }, { pixelRatio: ICON_RATIO });
    };
    map.on('styleimagemissing', onMissing);
    return () => { map.off('styleimagemissing', onMissing); };
  }, [ref]);
  return null;
}

/** id of the icon of an object: its shape, its kind (an expression) and its colour (an expression). */
export function iconImage(shape: Shape, kind: ExpressionSpecification, color: ExpressionSpecification): ExpressionSpecification {
  return x(['concat', `abf:${shape}:`, kind, ':', color]);
}

/** Size of the icon from the half size of the shape in px; the fine kinds at the smallest class take the next class. */
export function iconSize(rad: ExpressionSpecification, kind: ExpressionSpecification): ExpressionSpecification {
  const r = x(['case', ['all', fineCondition(kind), ['<=', rad, SIZE_RADII[0]]], SIZE_RADII[1], rad]);
  return x(['/', ['*', r, 2], DRAWN]);
}

export function renderSymbols(l: LayerEntry, d: Display & { size_field: string }, ctx: ModuleCtx) {
  const shape = shapeOf(d) as Shape;
  const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
  const sl = l.tiles.source_layer;
  const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
  const counted = isCounted(d);
  const typed = isTyped(d);
  const rad = counted ? placeRadius(d as Counted & { size_field: string }) : radiusExpression(d);
  const unknown = unknownCondition(d);
  const zero = zeroCondition(d);
  const kind = kindExpression(d, zero);
  // a type keeps its colour even when the size is unknown; a layer without types: the colour of the layer, grey for unknown
  const color = typed ? typeColorExpression(d as Typed, 'fill') : x(['case', unknown, UNKNOWN_COLOR, colorOf(d)]);
  // Filter by operator type (Atlas places): one group at a time; filters by field value (display.filters): several values
  const column = filterColumn(d, ctx.typeFilter);
  const group = column ? ctx.typeFilter : null;
  const shown = group && column && counted ? groupShown(d as Counted & Typed, group, column) : null;
  const isBadge = counted ? badgeCondition(d as Counted) : null;
  const byValue = filterExpression(d, ctx.layerFilters[l.layer_id]);
  const all = (...f: (ExpressionSpecification | null)[]) => {
    const a = f.filter(Boolean);
    return a.length === 0 ? null : a.length === 1 ? a[0] : (['all', ...a] as unknown as ExpressionSpecification);
  };
  const notBadge = isBadge ? x(['!', isBadge]) : null;
  const ptFilter = all(notBadge && shown ? x(['all', notBadge, ['==', ['get', (d as Typed).color_field], group]]) : notBadge, byValue);
  const hitFilter = all(shown, byValue);
  const badgeFilter = isBadge ? (shown ? x(['all', isBadge, ['>', ['to-number', ['get', column as string], 0], 0]]) : isBadge) : null;
  const countGet = counted ? x(['get', ctx.typeFilter && column ? column : (d as Counted).count_field]) : null;
  const selFilter = x(['==', ['get', 'record_id'], sel ?? '']);
  const selVis = visibility === 'visible' && sel ? 'visible' : 'none';
  const around = num(rad, 5);
  const f = (v: ExpressionSpecification | null) => (v ? { filter: v } : {});
  return (
    <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
      <Layer
        id={`${l.layer_id}-pt`}
        type="symbol"
        source-layer={sl}
        beforeId={ctx.before}
        {...f(ptFilter)}
        layout={{
          visibility,
          'icon-image': iconImage(shape, kind, color),
          'icon-size': iconSize(rad, kind),
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          // larger icons first, so that small ones stay on top of them
          'symbol-sort-key': x(['-', 0, rad]),
        }}
        paint={{ 'icon-opacity': 0.95 }}
      />
      {badgeFilter && countGet && (
        <>
          {/* Bigger numbers on top of smaller ones. A badge is neutral and has no kind of status: the statuses of its records are mixed. */}
          <Layer
            id={`${l.layer_id}-badge`}
            type="symbol"
            source-layer={sl}
            beforeId={ctx.before}
            filter={badgeFilter}
            layout={{ visibility, 'icon-image': iconId(shape, 'fill', BADGE_COLOR), 'icon-size': (2 * BADGE_RADIUS) / DRAWN, 'icon-allow-overlap': true, 'icon-ignore-placement': true, 'symbol-sort-key': x(['-', 0, countGet]) }}
          />
          <Layer
            id={`${l.layer_id}-badge-n`}
            type="symbol"
            source-layer={sl}
            beforeId={ctx.before}
            filter={badgeFilter}
            layout={{ visibility, 'text-field': x(['to-string', countGet]), 'text-font': ['Noto Sans Regular'], 'text-size': 12, 'text-allow-overlap': true, 'text-ignore-placement': true }}
            paint={{ 'text-color': '#ffffff' }}
          />
        </>
      )}
      <Layer id={`${l.layer_id}-hit`} type="circle" source-layer={sl} beforeId={ctx.before} {...f(hitFilter)} layout={{ visibility }} paint={{ 'circle-radius': x(['max', 9, num(rad, 3)]), 'circle-color': '#ffffff', 'circle-opacity': 0.01 }} />
      <Layer id={`${l.layer_id}-sel-under`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': around, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.surface, 'circle-stroke-width': 5.5 }} />
      <Layer id={`${l.layer_id}-sel`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': around, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.selected, 'circle-stroke-width': 2.5 }} />
    </Source>
  );
}

// ---- Legend marks (SVG, the same shapes and kinds as the icons) ----

/** One mark: shape, kind, colour, half size in px. */
export function Mark({ shape, kind = 'fill', color, r = 6 }: { shape: Shape; kind?: Kind; color: string; r?: number }) {
  const c = 14;
  const id = `h-${kind}-${color.slice(1)}-${shape}`;
  const body = (props: React.SVGProps<SVGElement>) => (shape === 'circle' ? <circle cx={c} cy={c} r={r} {...(props as React.SVGProps<SVGCircleElement>)} /> : <rect x={c - r} y={c - r} width={2 * r} height={2 * r} {...(props as React.SVGProps<SVGRectElement>)} />);
  const halo = body({ fill: 'none', stroke: COLORS.surface, strokeOpacity: 0.9, strokeWidth: 4 });
  const w = Math.max(1.5, r * 0.22);
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden className="shrink-0">
      {kind === 'hatch' && (
        <defs>
          <clipPath id={id}>{body({})}</clipPath>
        </defs>
      )}
      {halo}
      {kind === 'fill' && body({ fill: color })}
      {kind === 'pale' && <>{body({ fill: COLORS.surface, fillOpacity: 0.75 })}{body({ fill: color, fillOpacity: 0.38, stroke: color, strokeOpacity: 0.85, strokeWidth: 1.4 })}</>}
      {kind !== 'fill' && kind !== 'pale' && body({ fill: COLORS.surface, fillOpacity: 0.6 })}
      {kind === 'hatch' && (
        <g clipPath={`url(#${id})`} stroke={color} strokeWidth={w * 1.1}>
          {[-12, -6, 0, 6, 12].map((k) => <line key={k} x1={c - r + k - 2} y1={c + r + 2} x2={c + r + k + 2} y2={c - r - 2} />)}
        </g>
      )}
      {kind !== 'fill' && kind !== 'pale' && body({ fill: 'none', stroke: color, strokeWidth: w })}
      {kind === 'q' && <text x={c} y={c} textAnchor="middle" dominantBaseline="central" fontSize={r * 1.7} fontWeight="bold" fill={color}>?</text>}
      {kind === 'x' && <path d={`M${c - r * 0.5} ${c - r * 0.5}L${c + r * 0.5} ${c + r * 0.5}M${c + r * 0.5} ${c - r * 0.5}L${c - r * 0.5} ${c + r * 0.5}`} stroke={color} strokeWidth={w} strokeLinecap="round" />}
    </svg>
  );
}

/** One line of a filter: a tick box with the label (and the colour of a type). */
function Tick({ on, label, mark, onClick, disabled }: { on: boolean; label: string; mark?: React.ReactNode; onClick: () => void; disabled?: boolean }) {
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
        {mark}
        <span>{label}</span>
      </button>
    </li>
  );
}

/** A filter: "All" and the values; several may be ticked; nothing ticked is "All". */
function FilterList({ layerId, f, chosen, marks, onLayerFilter }: { layerId: string; f: NonNullable<ReturnType<typeof typeFilterOf>>; chosen: string[]; marks?: Record<string, React.ReactNode>; onLayerFilter?: (layerId: string, field: string, values: string[]) => void }) {
  const set = (v: string[]) => onLayerFilter?.(layerId, f.field, v);
  return (
    <ul className="space-y-0" role="group" aria-label={f.title}>
      <Tick on={chosen.length === 0} label="All" disabled={!onLayerFilter} onClick={() => set([])} />
      {f.values.map((v) => (
        <Tick key={v.value} on={chosen.includes(v.value)} label={v.label} mark={marks?.[v.value]} disabled={!onLayerFilter} onClick={() => set(chosen.includes(v.value) ? chosen.filter((y) => y !== v.value) : [...chosen, v.value])} />
      ))}
    </ul>
  );
}

/** Legend of a layer of typed icons (the power plants): the types (a filter), size classes, then the other filters. */
export function TypedLegend({ layer, d, layerFilters, onLayerFilter }: { layer: LayerEntry; d: Display; layerFilters?: LayerFilters; onLayerFilter?: (layerId: string, field: string, values: string[]) => void }) {
  const shape = shapeOf(d) ?? 'circle';
  const typed = isTyped(d) ? (d as Typed) : null;
  const typeFilter = typeFilterOf(d);
  const classes = d.size_classes && d.size_classes.length > 0 ? d.size_classes : d.legend_size_labels ? Object.keys(d.legend_size_labels) : null;
  const breaks = d.size_breaks ?? [];
  const sizeText: string[] = classes ? classes.map((c, i) => d.legend_size_labels?.[c] ?? sizeLabels(breaks, 'MW')[i] ?? c) : breaks.length ? sizeLabels(breaks, 'MW') : [];
  const chosen = effectiveFilters(d, layerFilters?.[layer.layer_id]);
  const marks = typed ? Object.fromEntries(typed.color_classes.map((c, i) => [c, <Mark key={c} shape={shape} color={classColor(typed, c, i).fill} r={5} />])) : undefined;
  return (
    <div className="mt-3 first:mt-0">
      <h3 className="mb-1 text-[13px] font-semibold text-ink">{d.legend_title ?? layer.title}</h3>
      {d.legend_note && <p className="mb-1 text-xs text-muted">{d.legend_note}</p>}
      {typeFilter && <FilterList layerId={layer.layer_id} f={typeFilter} chosen={chosen[typeFilter.field] ?? []} marks={marks} onLayerFilter={onLayerFilter} />}
      {sizeText.length > 0 && (
        <ul className="mt-1 space-y-0 border-t border-line pt-1">
          {sizeText.map((t, i) => (
            <li key={t} className="flex items-center gap-2">
              <Mark shape={shape} color="#6b6f76" r={SIZE_RADII[Math.min(i, SIZE_RADII.length - 1)]} />
              <span>{t}</span>
            </li>
          ))}
        </ul>
      )}
      {filtersOf(d).filter((fl) => fl.field !== typeFilter?.field).map((fl) => (
        <fieldset key={fl.field} className="mt-2 border-t border-line pt-2">
          {fl.title && <legend className="mb-1 text-[13px] font-semibold text-ink">{fl.title}</legend>}
          {fl.note && <p className="mb-1 text-xs text-muted">{fl.note}</p>}
          <FilterList layerId={layer.layer_id} f={fl} chosen={chosen[fl.field] ?? []} onLayerFilter={onLayerFilter} />
        </fieldset>
      ))}
    </div>
  );
}
