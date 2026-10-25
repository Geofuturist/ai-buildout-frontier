// Polygon layers: fill by value classes (units such as counties or departments).
import { Layer, Source } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import { COLORS, fillColorExpression, legendClasses } from '@/lib/style';
import Swatch from './Swatch';
import type { GeometryModule } from './types';

const COVERED = ['==', ['get', 'coverage_status'], 'covered'] as ExpressionSpecification;
const NOT_COVERED = ['!=', ['get', 'coverage_status'], 'covered'] as ExpressionSpecification;

const polygonModule: GeometryModule = {
  type: 'polygon',
  exclusive: true,
  keyField: 'unit_id',
  recordDownload: true,
  accepts: (layer, meta) => layer.tiles.geometry_type === 'polygon' && Boolean(meta?.display?.value_field),

  hitLayerIds: (id) => [`${id}-fill`, `${id}-nc-hit`],

  renderLayers(layers, ctx) {
    return layers.map((l) => {
      const d = ctx.metas[l.meta_id].display!;
      const field = d.value_field!;
      const vis = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
      const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
      const sl = l.tiles.source_layer;
      return (
        <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
          <Layer
            id={`${l.layer_id}-fill`}
            type="fill"
            source-layer={sl}
            beforeId={ctx.before}
            filter={COVERED}
            layout={{ visibility: vis }}
            paint={{ 'fill-color': fillColorExpression(field, d.breaks ?? [], l.domain, Boolean(d.breaks_fixed)) }}
          />
          {d.zero_class && (
            <Layer
              id={`${l.layer_id}-zero`}
              type="line"
              source-layer={sl}
              beforeId={ctx.before}
              filter={['all', COVERED, ['==', ['get', field], 0]] as ExpressionSpecification}
              layout={{ visibility: vis }}
              paint={{ 'line-color': COLORS.zeroStroke, 'line-width': 0.5 }}
            />
          )}
          {/* Not covered: no fill, dashed outline (fallback approved in SPEC_WEB section 6) */}
          <Layer
            id={`${l.layer_id}-nc`}
            type="line"
            source-layer={sl}
            beforeId={ctx.before}
            filter={NOT_COVERED}
            layout={{ visibility: vis }}
            paint={{ 'line-color': COLORS.notCovered, 'line-width': 0.8, 'line-dasharray': [2, 2] }}
          />
          <Layer
            id={`${l.layer_id}-nc-hit`}
            type="fill"
            source-layer={sl}
            beforeId={ctx.before}
            filter={NOT_COVERED}
            layout={{ visibility: vis }}
            paint={{ 'fill-color': COLORS.surface, 'fill-opacity': 0.01 }}
          />
          <Layer
            id={`${l.layer_id}-sel-under`}
            type="line"
            source-layer={sl}
            beforeId={ctx.before}
            filter={['==', ['get', 'unit_id'], sel ?? ''] as ExpressionSpecification}
            layout={{ visibility: vis === 'visible' && sel ? 'visible' : 'none' }}
            paint={{ 'line-color': COLORS.surface, 'line-width': 5 }}
          />
          <Layer
            id={`${l.layer_id}-sel`}
            type="line"
            source-layer={sl}
            beforeId={ctx.before}
            filter={['==', ['get', 'unit_id'], sel ?? ''] as ExpressionSpecification}
            layout={{ visibility: vis === 'visible' && sel ? 'visible' : 'none' }}
            paint={{ 'line-color': COLORS.selected, 'line-width': 2.5 }}
          />
        </Source>
      );
    });
  },

  Legend({ layers, metas }) {
    // One polygon layer is active at a time
    const meta = layers[0] ? metas[layers[0].meta_id] : null;
    const d = meta?.display;
    if (!d || !d.breaks || !d.value_field) return null;
    // every unit of the frame is covered (e.g. the world count layer): no "not covered" row
    const cov = meta?.coverage;
    const allCovered = Boolean(cov && cov.n_units_frame !== null && cov.n_units_frame === cov.n_units_covered);
    const classes = legendClasses(d.breaks, d.unit ?? '', Boolean(d.zero_class), layers[0].domain, Boolean(d.breaks_fixed));
    return (
      <>
        <h3 className="mb-1 text-[13px] font-semibold text-ink">{d.legend_title}</h3>
        <ul className="space-y-1">
          {classes.map((c) => (
            <li key={c.label} className="flex items-center gap-2">
              <Swatch color={c.color} stroke={c.color === COLORS.zero ? COLORS.zeroStroke : undefined} />
              <span>{c.label}</span>
            </li>
          ))}
          <li className="flex items-center gap-2">
            <Swatch color={COLORS.noValue} />
            <span>Covered, no value in the source</span>
          </li>
          {!allCovered && (
            <li className="flex items-center gap-2">
              <Swatch stroke={COLORS.notCovered} dashed />
              <span>Not covered (no fill, dashed outline)</span>
            </li>
          )}
        </ul>
      </>
    );
  },
};

export default polygonModule;
