// Point layers (registry points such as data centers): one shape, one colour (plum), no size, on a light ring so
// the dots stay readable over dark fills.
// Position accuracy: a filled dot is a site-level position; a hollow ring is approximate (never overstated).
import { Layer, Source } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import { COLORS } from '@/lib/style';
import type { GeometryModule } from './types';

const SITE_LEVEL = 'site';
// dot radius 5 + half of the 1.8 px outline + 1.5 px of ring
const RING_RADIUS = 7.4;
// Position accuracy is a contract field of every point layer (ADR 6.2): site | city | none
const PRECISION_FIELD = 'coord_precision';

const pointModule: GeometryModule = {
  type: 'point',
  exclusive: false,
  keyField: 'record_id',
  recordDownload: true,
  accepts: (layer) => layer.tiles.geometry_type === 'point',

  hitLayerIds: (id) => [`${id}-hit`],

  renderLayers(layers, ctx) {
    return layers.map((l) => {
      const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
      const sl = l.tiles.source_layer;
      const sel = ctx.selected && ctx.selected.layerId === l.layer_id ? ctx.selected.key : null;
      // filled = site-level position; anything else is drawn hollow, so accuracy is never overstated
      const fill = ['case', ['==', ['get', PRECISION_FIELD], SITE_LEVEL], COLORS.point, 'rgba(252,252,251,0.35)'] as ExpressionSpecification;
      return (
        <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
          {/* Light ring: 1.5 px outside the outline of the dot (SPEC_WEB r8 0.5 p.1) */}
          <Layer
            id={`${l.layer_id}-ring`}
            type="circle"
            source-layer={sl}
            beforeId={ctx.before}
            layout={{ visibility }}
            paint={{ 'circle-radius': RING_RADIUS, 'circle-color': COLORS.surface, 'circle-opacity': 0.9 }}
          />
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
            id={`${l.layer_id}-sel-under`}
            type="circle"
            source-layer={sl}
            beforeId={ctx.before}
            filter={['==', ['get', 'record_id'], sel ?? ''] as ExpressionSpecification}
            layout={{ visibility: visibility === 'visible' && sel ? 'visible' : 'none' }}
            paint={{ 'circle-radius': 10, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': COLORS.surface, 'circle-stroke-width': 5.5 }}
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

  formatValue(field, value) {
    if (field.name === PRECISION_FIELD) {
      if (value === SITE_LEVEL) return 'Site level';
      if (value === 'city') return 'Approximate (commune level)';
    }
    return null;
  },

  Legend({ layers }) {
    if (layers.length === 0) return null;
    const dot = (filled: boolean) => (
      <svg width="24" height="16" aria-hidden className="shrink-0">
        <circle cx="12" cy="8" r={RING_RADIUS} fill={COLORS.surface} fillOpacity="0.9" />
        <circle cx="12" cy="8" r="5" fill={filled ? COLORS.point : 'rgba(252,252,251,0.35)'} stroke={COLORS.point} strokeWidth="1.8" />
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
