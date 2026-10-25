// Point layers (registry points such as data centers).
// Two kinds, told apart by the meta of the layer:
//  - sized (display.size_field): radius by class, a hollow ring for 0, a small grey dot for "unknown"; every point is a
//    town-level place, so all are drawn translucent with a light ring (never an exact site)
//  - plain: one plum dot; filled = site-level position, hollow = approximate (coord_precision)
import { Layer, Source } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import type { LayerEntry, Meta } from '@/lib/data';
import { COLORS } from '@/lib/style';
import {
  BADGE_COLOR, BADGE_RADII, RING_EXTRA, SIZE_RADII, UNKNOWN_COLOR, UNKNOWN_RADIUS,
  badgeCondition, badgeRadius, badgeTextSize, colorOf, countLabels, filterColumn, groupShown, isCounted, isSized, isTyped, placeRadius, radiusExpression, sizeLabels, typeColor, typeColorExpression, unknownCondition, zeroCondition,
} from '@/lib/pointSize';
import type { Counted, Typed } from '@/lib/pointSize';
import type { GeometryModule, ModuleCtx } from './types';

const SITE_LEVEL = 'site';
// dot radius 5 + half of the 1.8 px outline + 1.5 px of ring
const RING_RADIUS = 7.4;
// Position accuracy is a contract field of every point layer (ADR 6.2): site | city | none
const PRECISION_FIELD = 'coord_precision';

type Display = NonNullable<Meta['display']>;
const num = (e: ExpressionSpecification, k: number) => ['+', e, k] as unknown as ExpressionSpecification;

function renderPlain(l: LayerEntry, ctx: ModuleCtx) {
  const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
  const sl = l.tiles.source_layer;
  const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
  // filled = site-level position; anything else is drawn hollow, so accuracy is never overstated
  const fill = ['case', ['==', ['get', PRECISION_FIELD], SITE_LEVEL], COLORS.point, 'rgba(252,252,251,0.35)'] as ExpressionSpecification;
  return (
    <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
      {/* Light ring: 1.5 px outside the outline of the dot (SPEC_WEB r8 0.5 p.1) */}
      <Layer id={`${l.layer_id}-ring`} type="circle" source-layer={sl} beforeId={ctx.before} layout={{ visibility }} paint={{ 'circle-radius': RING_RADIUS, 'circle-color': COLORS.surface, 'circle-opacity': 0.9 }} />
      <Layer id={`${l.layer_id}-pt`} type="circle" source-layer={sl} beforeId={ctx.before} layout={{ visibility }} paint={{ 'circle-radius': 5, 'circle-color': fill, 'circle-stroke-color': COLORS.point, 'circle-stroke-width': 1.8 }} />
      <Layer id={`${l.layer_id}-hit`} type="circle" source-layer={sl} beforeId={ctx.before} layout={{ visibility }} paint={{ 'circle-radius': 12, 'circle-color': '#ffffff', 'circle-opacity': 0.01 }} />
      <Layer id={`${l.layer_id}-sel-under`} type="circle" source-layer={sl} beforeId={ctx.before} filter={['==', ['get', 'record_id'], sel ?? ''] as ExpressionSpecification} layout={{ visibility: visibility === 'visible' && sel ? 'visible' : 'none' }} paint={{ 'circle-radius': 10, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.surface, 'circle-stroke-width': 5.5 }} />
      <Layer id={`${l.layer_id}-sel`} type="circle" source-layer={sl} beforeId={ctx.before} filter={['==', ['get', 'record_id'], sel ?? ''] as ExpressionSpecification} layout={{ visibility: visibility === 'visible' && sel ? 'visible' : 'none' }} paint={{ 'circle-radius': 10, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.selected, 'circle-stroke-width': 2.5 }} />
    </Source>
  );
}

function renderSized(l: LayerEntry, d: Display & { size_field: string }, ctx: ModuleCtx) {
  const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
  const sl = l.tiles.source_layer;
  const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
  const color = colorOf(d);
  const radius = radiusExpression(d);
  const unknown = unknownCondition(d);
  const zero = zeroCondition(d);
  const hollow = zero ? (['any', zero] as unknown as ExpressionSpecification) : null;
  // translucent fill: the place is the town, not the site
  const fillColor: ExpressionSpecification = hollow
    ? (['case', unknown, UNKNOWN_COLOR, hollow, 'rgba(255,255,255,0)', color] as unknown as ExpressionSpecification)
    : (['case', unknown, UNKNOWN_COLOR, color] as unknown as ExpressionSpecification);
  const fillOpacity = ['case', unknown, 0.9, 0.5] as unknown as ExpressionSpecification;
  const strokeWidth: ExpressionSpecification = hollow
    ? (['case', unknown, 0, hollow, 1.8, 1.2] as unknown as ExpressionSpecification)
    : (['case', unknown, 0, 1.2] as unknown as ExpressionSpecification);
  const selFilter = ['==', ['get', 'record_id'], sel ?? ''] as ExpressionSpecification;
  const selVis = visibility === 'visible' && sel ? 'visible' : 'none';
  return (
    <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
      <Layer id={`${l.layer_id}-ring`} type="circle" source-layer={sl} beforeId={ctx.before} layout={{ visibility }} paint={{ 'circle-radius': num(radius, RING_EXTRA), 'circle-color': COLORS.surface, 'circle-opacity': 0.85 }} />
      <Layer
        id={`${l.layer_id}-pt`}
        type="circle"
        source-layer={sl}
        beforeId={ctx.before}
        layout={{ visibility }}
        paint={{ 'circle-radius': radius, 'circle-color': fillColor, 'circle-opacity': fillOpacity, 'circle-stroke-color': color, 'circle-stroke-width': strokeWidth, 'circle-stroke-opacity': 1 }}
      />
      <Layer id={`${l.layer_id}-hit`} type="circle" source-layer={sl} beforeId={ctx.before} layout={{ visibility }} paint={{ 'circle-radius': ['max', 9, num(radius, 3)] as unknown as ExpressionSpecification, 'circle-color': '#ffffff', 'circle-opacity': 0.01 }} />
      <Layer id={`${l.layer_id}-sel-under`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': num(radius, 5), 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.surface, 'circle-stroke-width': 5.5 }} />
      <Layer id={`${l.layer_id}-sel`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': num(radius, 5), 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.selected, 'circle-stroke-width': 2.5 }} />
    </Source>
  );
}

/**
 * Places (display.count_field): a place with `count_breaks[0]` records or more is a badge with the number, sized by
 * the badge class; a place with fewer is a point of its record, sized by the size class as in a sized layer
 * (a place whose one record has no class is the grey "unknown" dot). Every number comes from the tiles.
 */
function renderCounted(l: LayerEntry, d: Counted & { size_field: string }, ctx: ModuleCtx) {
  const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
  const sl = l.tiles.source_layer;
  const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
  const typed = isTyped(d);
  // Filter by type: one group at a time; the number and size of a badge come from the column of that group
  const column = filterColumn(d, ctx.typeFilter);
  const group = column ? ctx.typeFilter : null;
  const numField = column ?? d.count_field;
  const color = colorOf(d);
  const radius = placeRadius(d, column ?? undefined);
  const isBadge = badgeCondition(d);
  const notBadge = ['!', isBadge] as unknown as ExpressionSpecification;
  const unknown = unknownCondition(d);
  // Colour by operator type when the layer has it (a place with one record); a place with one record whose class is
  // unknown keeps its type colour as a small dot
  const fillColor = typed
    ? typeColorExpression(d as Typed, 'fill')
    : (['case', unknown, UNKNOWN_COLOR, color] as unknown as ExpressionSpecification);
  const strokeColor = typed ? typeColorExpression(d as Typed, 'stroke') : color;
  const fillOpacity = ['case', unknown, 0.9, 0.5] as unknown as ExpressionSpecification;
  const strokeWidth = (typed ? ['case', unknown, 1, 1.2] : ['case', unknown, 0, 1.2]) as unknown as ExpressionSpecification;
  const selFilter = ['==', ['get', 'record_id'], sel ?? ''] as ExpressionSpecification;
  const selVis = visibility === 'visible' && sel ? 'visible' : 'none';
  const countGet = ['get', numField] as unknown as ExpressionSpecification;
  const shown = group && column ? groupShown(d as Counted & Typed, group, column) : null;
  const ptFilter = shown ? (['all', notBadge, ['==', ['get', (d as Typed).color_field], group]] as unknown as ExpressionSpecification) : notBadge;
  const badgeFilter = shown ? (['all', isBadge, ['>', ['to-number', ['get', column as string], 0], 0]] as unknown as ExpressionSpecification) : isBadge;
  return (
    <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
      <Layer id={`${l.layer_id}-ring`} type="circle" source-layer={sl} beforeId={ctx.before} {...(shown ? { filter: shown } : {})} layout={{ visibility }} paint={{ 'circle-radius': num(radius, RING_EXTRA), 'circle-color': COLORS.surface, 'circle-opacity': 0.85 }} />
      <Layer
        id={`${l.layer_id}-pt`}
        type="circle"
        source-layer={sl}
        beforeId={ctx.before}
        filter={ptFilter}
        layout={{ visibility }}
        paint={{ 'circle-radius': radiusExpression(d), 'circle-color': fillColor, 'circle-opacity': fillOpacity, 'circle-stroke-color': strokeColor, 'circle-stroke-width': strokeWidth, 'circle-stroke-opacity': 1 }}
      />
      {/* Bigger numbers on top of smaller ones where badges overlap. A badge is neutral: it is not coloured by the
          group that prevails, which would be our reading of the mix. */}
      <Layer
        id={`${l.layer_id}-badge`}
        type="circle"
        source-layer={sl}
        beforeId={ctx.before}
        filter={badgeFilter}
        layout={{ visibility, 'circle-sort-key': countGet }}
        paint={{ 'circle-radius': badgeRadius(d, column ?? undefined), 'circle-color': BADGE_COLOR, 'circle-opacity': 0.92, 'circle-stroke-color': COLORS.surface, 'circle-stroke-width': 1.2 }}
      />
      <Layer
        id={`${l.layer_id}-badge-n`}
        type="symbol"
        source-layer={sl}
        beforeId={ctx.before}
        filter={badgeFilter}
        layout={{
          visibility,
          'text-field': ['to-string', countGet] as unknown as ExpressionSpecification,
          'text-font': ['Noto Sans Regular'],
          'text-size': badgeTextSize(d, column ?? undefined),
          'text-allow-overlap': true,
          'text-ignore-placement': true,
        }}
        paint={{ 'text-color': '#ffffff' }}
      />
      <Layer id={`${l.layer_id}-hit`} type="circle" source-layer={sl} beforeId={ctx.before} {...(shown ? { filter: shown } : {})} layout={{ visibility }} paint={{ 'circle-radius': ['max', 9, num(radius, 3)] as unknown as ExpressionSpecification, 'circle-color': '#ffffff', 'circle-opacity': 0.01 }} />
      <Layer id={`${l.layer_id}-sel-under`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': num(radius, 5), 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.surface, 'circle-stroke-width': 5.5 }} />
      <Layer id={`${l.layer_id}-sel`} type="circle" source-layer={sl} beforeId={ctx.before} filter={selFilter} layout={{ visibility: selVis }} paint={{ 'circle-radius': num(radius, 5), 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.selected, 'circle-stroke-width': 2.5 }} />
    </Source>
  );
}

function Badge({ r, n }: { r: number; n: string }) {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" aria-hidden className="shrink-0">
      <circle cx="20" cy="20" r={r} fill={BADGE_COLOR} fillOpacity="0.92" stroke={COLORS.surface} strokeWidth="1.2" />
      <text x="20" y="20" textAnchor="middle" dominantBaseline="central" fontSize={r > 14 ? 12.5 : 11} fill="#ffffff">{n}</text>
    </svg>
  );
}

function Dot({ r, color, fill, stroke, w = 1.2, opacity = 0.5, ring = true }: { r: number; color?: string; fill?: string; stroke?: string; w?: number; opacity?: number; ring?: boolean }) {
  const c = 14;
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden className="shrink-0">
      {ring && <circle cx={c} cy={c} r={r + RING_EXTRA} fill={COLORS.surface} fillOpacity="0.85" />}
      <circle cx={c} cy={c} r={r} fill={fill ?? color} fillOpacity={opacity} stroke={stroke ?? color} strokeWidth={w} />
    </svg>
  );
}

const pointModule: GeometryModule = {
  type: 'point',
  exclusive: false,
  keyField: 'record_id',
  recordDownload: true,
  accepts: (layer) => layer.tiles.geometry_type === 'point',

  hitLayerIds: (id) => [`${id}-hit`],

  renderLayers(layers, ctx) {
    const sizedOf = (l: LayerEntry) => ctx.metas[l.meta_id]?.display;
    const rank = (l: LayerEntry) => {
      const d = sizedOf(l);
      if (!isSized(d)) return 0;
      // class fields under numeric ones: the numeric layer is drawn on top
      return d.size_classes?.length ? 1 : 2;
    };
    return [...layers].sort((a, b) => rank(a) - rank(b)).map((l) => {
      const d = sizedOf(l);
      if (isSized(d) && isCounted(d)) return renderCounted(l, d, ctx);
      return isSized(d) ? renderSized(l, d, ctx) : renderPlain(l, ctx);
    });
  },

  formatValue(field, value) {
    if (field.name === PRECISION_FIELD) {
      if (value === SITE_LEVEL) return 'Site level';
      if (value === 'city') return 'Approximate (commune level)';
    }
    return null;
  },

  Legend({ layers, metas, typeFilter, onTypeFilter }) {
    if (layers.length === 0) return null;
    const sized = layers.filter((l) => isSized(metas[l.meta_id]?.display));
    const plain = layers.filter((l) => !isSized(metas[l.meta_id]?.display));
    const first = sized[0] ? (metas[sized[0].meta_id].display as Display & { size_field: string }) : null;
    const withZero = sized.some((l) => metas[l.meta_id].display?.zero_class);
    const unit = first ? metas[sized.find((l) => !metas[l.meta_id].display?.size_classes?.length)?.meta_id ?? sized[0].meta_id].fields.find((f) => f.name === first.size_field)?.unit ?? '' : '';
    const counted = sized.map((l) => metas[l.meta_id].display).find((x) => isCounted(x)) as Counted | undefined;
    const typed = sized.map((l) => metas[l.meta_id].display).find((x) => isTyped(x)) as Typed | undefined;
    const breaks = first?.size_breaks ?? [];
    const labels = breaks.length ? sizeLabels(breaks, unit || 'MW') : [];
    const plainDot = (filled: boolean) => (
      <svg width="24" height="16" aria-hidden className="shrink-0">
        <circle cx="12" cy="8" r={RING_RADIUS} fill={COLORS.surface} fillOpacity="0.9" />
        <circle cx="12" cy="8" r="5" fill={filled ? COLORS.point : 'rgba(252,252,251,0.35)'} stroke={COLORS.point} strokeWidth="1.8" />
      </svg>
    );
    return (
      <>
        {sized.length > 0 && first && (
          <>
            <h3 className="mb-1 mt-3 text-[13px] font-semibold text-ink">{first.legend_title ?? 'Size'}</h3>
            <ul className="space-y-0.5">
              {sized.map((l) => (
                <li key={l.layer_id} className="flex items-center gap-2">
                  <Dot r={5} color={isTyped(metas[l.meta_id].display) ? BADGE_COLOR : colorOf(metas[l.meta_id].display as Display)} />
                  <span>
                    {l.title}
                    {metas[l.meta_id].display?.legend_layer_note && <span className="block text-xs text-muted">{metas[l.meta_id].display?.legend_layer_note}</span>}
                  </span>
                </li>
              ))}
            </ul>
            {labels.length > 0 && (
              <ul className="mt-1 space-y-0 border-t border-line pt-1">
                {labels.map((t, i) => (
                  <li key={t} className="flex items-center gap-2">
                    <Dot r={SIZE_RADII[Math.min(i, SIZE_RADII.length - 1)]} color="#6b6f76" />
                    <span>{t}</span>
                  </li>
                ))}
                {withZero && first.legend_zero && (
                  <li className="flex items-center gap-2">
                    <Dot r={SIZE_RADII[0]} color="#6b6f76" fill="rgba(255,255,255,0)" w={1.8} opacity={0} />
                    <span>{first.legend_zero}</span>
                  </li>
                )}
                {first.legend_unknown && (
                  <li className="flex items-center gap-2">
                    <Dot r={UNKNOWN_RADIUS} color={UNKNOWN_COLOR} w={0} opacity={0.9} />
                    <span>{first.legend_unknown}</span>
                  </li>
                )}
                {first.legend_point && (
                  <li className="flex items-center gap-2">
                    <Dot r={5} color="#6b6f76" />
                    <span>{first.legend_point}</span>
                  </li>
                )}
              </ul>
            )}
            {counted && (
              <ul className="mt-1 space-y-0 border-t border-line pt-1">
                <li className="text-xs text-ink2">Place with several records (the number is the count):</li>
                {(counted.legend_count_classes?.length === counted.count_breaks.length ? counted.legend_count_classes : countLabels(counted.count_breaks)).map((t, i) => (
                  <li key={t} className="flex items-center gap-2">
                    <Badge r={Math.min(BADGE_RADII[Math.min(i, BADGE_RADII.length - 1)], 19)} n={String(counted.count_breaks[i])} />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            )}
            {first.legend_note && <p className="mt-1 text-xs text-muted">{first.legend_note}</p>}
            {typed && (
              <div className="mt-2 border-t border-line pt-2" role="radiogroup" aria-label={typed.legend_type_title ?? 'Type'}>
                <h3 className="mb-1 text-[13px] font-semibold text-ink">{typed.legend_type_title ?? 'Type'}</h3>
                {typed.legend_type_note && <p className="mb-1 text-xs text-muted">{typed.legend_type_note}</p>}
                <ul className="space-y-0">
                  {[{ key: null as string | null, label: typed.legend_type_filter_all ?? 'All types', color: null as string | null }, ...typed.color_classes.map((c, i) => ({ key: c as string | null, label: typed.legend_type_labels?.[c] ?? c, color: typeColor(i).fill as string | null }))].map((o) => {
                    const on = (typeFilter ?? null) === o.key;
                    const canFilter = o.key === null || Boolean(typed.filter_fields?.[o.key]);
                    return (
                      <li key={o.key ?? 'all'}>
                        <button
                          type="button"
                          role="radio"
                          aria-checked={on}
                          disabled={!onTypeFilter || !canFilter}
                          className={`flex min-h-[32px] w-full items-center gap-2 rounded px-1 text-left hover:bg-[#eef3f3] ${on ? 'font-semibold' : ''}`}
                          onClick={() => onTypeFilter?.(o.key)}
                        >
                          <span aria-hidden className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${on ? 'border-[#0f6e6e]' : 'border-[#8a8f96]'}`}>
                            {on && <span className="h-2 w-2 rounded-full bg-[#0f6e6e]" />}
                          </span>
                          {o.color ? <span aria-hidden className="h-3 w-3 shrink-0 rounded-full border border-black/20" style={{ background: o.color }} /> : <span aria-hidden className="h-3 w-3 shrink-0" />}
                          <span>{o.label}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </>
        )}
        {plain.length > 0 && (
          <>
            <h3 className="mb-1 mt-3 text-[13px] font-semibold text-ink">Points</h3>
            <ul className="space-y-1">
              <li className="flex items-center gap-2">{plainDot(true)}<span>Position at the site</span></li>
              <li className="flex items-center gap-2">{plainDot(false)}<span>Approximate position (commune)</span></li>
            </ul>
          </>
        )}
      </>
    );
  },
};

export default pointModule;
