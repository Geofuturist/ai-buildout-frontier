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
  RING_EXTRA, SIZE_RADII, UNKNOWN_COLOR, UNKNOWN_RADIUS, colorOf, isSized, radiusExpression, sizeLabels, unknownCondition, zeroCondition,
} from '@/lib/pointSize';
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

  Legend({ layers, metas }) {
    if (layers.length === 0) return null;
    const sized = layers.filter((l) => isSized(metas[l.meta_id]?.display));
    const plain = layers.filter((l) => !isSized(metas[l.meta_id]?.display));
    const first = sized[0] ? (metas[sized[0].meta_id].display as Display & { size_field: string }) : null;
    const withZero = sized.some((l) => metas[l.meta_id].display?.zero_class);
    const unit = first ? metas[sized.find((l) => !metas[l.meta_id].display?.size_classes?.length)?.meta_id ?? sized[0].meta_id].fields.find((f) => f.name === first.size_field)?.unit ?? '' : '';
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
                  <Dot r={5} color={colorOf(metas[l.meta_id].display as Display)} />
                  <span>{l.title}</span>
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
            {first.legend_note && <p className="mt-1 text-xs text-muted">{first.legend_note}</p>}
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
