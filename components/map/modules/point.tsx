// Point layers (registry points such as data centers): one shape, one dark neutral colour, no size.
// Position accuracy: a filled dot is a site-level position; a hollow ring is approximate (never overstated).
import { Layer, Source } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import { COLORS } from '@/lib/style';
import type { GeometryModule } from './types';

const SITE_LEVEL = 'site';

const pointModule: GeometryModule = {
  type: 'point',
  exclusive: false,
  keyField: 'record_id',
  recordDownload: true,
  accepts: (layer) => layer.tiles.geometry_type === 'point',

  hitLayerIds: (id) => [`${id}-hit`],

  renderLayers(layers, ctx) {
    return layers.map((l) => {
      const precision = ctx.metas[l.meta_id].display?.value_field;
      const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
      const sl = l.tiles.source_layer;
      const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
      // No precision field in the meta: treat every point as approximate (hollow)
      const fill = precision
        ? (['case', ['==', ['get', precision], SITE_LEVEL], COLORS.point, 'rgba(252,252,251,0.35)'] as ExpressionSpecification)
        : 'rgba(252,252,251,0.35)';
      return (
        <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
          <Layer
            id={`${l.layer_id}-pt`}
            type="circle"
            source-layer={sl}
            beforeId={ctx.before}
            layout={{ visibility }}
            paint={{ 'circle-radius': 5, 'circle-color': fill, 'circle-stroke-color': COLORS.point, 'circle-stroke-width': 1.8 }}
          />
          <Layer
            id={`${l.layer_id}-hit`}
            type="circle"
            source-layer={sl}
            beforeId={ctx.before}
            layout={{ visibility }}
            paint={{ 'circle-radius': 12, 'circle-color': '#ffffff', 'circle-opacity': 0.01 }}
          />
          <Layer
            id={`${l.layer_id}-sel`}
            type="circle"
            source-layer={sl}
            beforeId={ctx.before}
            filter={['==', ['get', 'record_id'], sel ?? ''] as ExpressionSpecification}
            layout={{ visibility: visibility === 'visible' && sel ? 'visible' : 'none' }}
            paint={{ 'circle-radius': 10, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.selected, 'circle-stroke-width': 2.5 }}
          />
        </Source>
      );
    });
  },

  formatValue(field, value, meta) {
    if (field.name === meta.display?.value_field) {
      if (value === SITE_LEVEL) return 'Site level';
      if (value === 'city') return 'Approximate (commune level)';
    }
    return null;
  },

  Legend({ layers }) {
    if (layers.length === 0) return null;
    const dot = (filled: boolean) => (
      <svg width="24" height="14" aria-hidden className="shrink-0">
        <circle cx="12" cy="7" r="5" fill={filled ? COLORS.point : 'rgba(252,252,251,0.35)'} stroke={COLORS.point} strokeWidth="1.8" />
      </svg>
    );
    return (
      <>
        <h3 className="mb-1 mt-3 text-[13px] font-semibold text-ink">Points</h3>
        <ul className="space-y-1">
          <li className="flex items-center gap-2">{dot(true)}<span>Position at the site</span></li>
          <li className="flex items-center gap-2">{dot(false)}<span>Approximate position (commune)</span></li>
        </ul>
      </>
    );
  },
};

export default pointModule;
