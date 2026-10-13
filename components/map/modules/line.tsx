// Line layers: segments coloured and sized by voltage band (one legend for all transmission layers).
import { Layer, Source } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import { VOLTAGE_BANDS, bandColorExpression, bandWidthExpression } from '@/lib/style';
import { formatNumber } from '@/lib/format';
import type { GeometryModule } from './types';

const lineModule: GeometryModule = {
  type: 'line',
  exclusive: false,
  keyField: 'record_id',
  // Segment files are large: the card offers "Cite this segment" only
  recordDownload: false,
  accepts: (layer) => layer.tiles.geometry_type === 'line',

  hitLayerIds: (id) => [`${id}-hit`],

  renderLayers(layers, ctx) {
    return layers.map((l) => {
      const band = ctx.metas[l.meta_id].display?.value_field;
      if (!band) return null; // the meta names the band field in display.value_field
      const visibility = ctx.visible.has(l.layer_id) ? 'visible' : 'none';
      const sl = l.tiles.source_layer;
      return (
        <Source key={l.layer_id} id={l.layer_id} type="vector" url={`pmtiles://${l.tiles.url}`}>
          {/* Light casing under the lines, so dark steps stay visible over dark fills */}
          <Layer
            id={`${l.layer_id}-casing`}
            type="line"
            source-layer={sl}
            beforeId={ctx.before}
            filter={['!=', ['get', band], 'unknown'] as ExpressionSpecification}
            layout={{ visibility, 'line-cap': 'round' }}
            paint={{ 'line-color': '#fcfcfb', 'line-opacity': 0.8, 'line-width': bandWidthExpression(band, 1.2) }}
          />
          <Layer
            id={`${l.layer_id}-line`}
            type="line"
            source-layer={sl}
            beforeId={ctx.before}
            filter={['!=', ['get', band], 'unknown'] as ExpressionSpecification}
            layout={{ visibility, 'line-cap': 'round' }}
            paint={{ 'line-color': bandColorExpression(band), 'line-width': bandWidthExpression(band) }}
          />
          <Layer
            id={`${l.layer_id}-line-unknown`}
            type="line"
            source-layer={sl}
            beforeId={ctx.before}
            filter={['==', ['get', band], 'unknown'] as ExpressionSpecification}
            layout={{ visibility }}
            paint={{ 'line-color': '#8a8f96', 'line-width': 0.8, 'line-dasharray': [2, 2] }}
          />
          <Layer
            id={`${l.layer_id}-hit`}
            type="line"
            source-layer={sl}
            beforeId={ctx.before}
            layout={{ visibility }}
            paint={{ 'line-color': '#ffffff', 'line-opacity': 0.01, 'line-width': 12 }}
          />
        </Source>
      );
    });
  },

  formatValue(field, value, meta) {
    if (field.name === meta.display?.value_field) return VOLTAGE_BANDS.find((b) => b.id === value)?.label ?? null;
    // Voltages and other measures are never negative: a negative number is the source's "not recorded" marker
    if (typeof value === 'number' && value < 0) return 'Not recorded';
    if (typeof value === 'number') return `${formatNumber(value, 1)}${field.unit ? ` ${field.unit}` : ''}`;
    return null;
  },

  Legend({ layers }) {
    if (layers.length === 0) return null;
    return (
      <>
        <h3 className="mb-1 mt-3 text-[13px] font-semibold text-ink">Transmission line voltage</h3>
        <ul className="space-y-1">
          {VOLTAGE_BANDS.map((b) => (
            <li key={b.id} className="flex items-center gap-2">
              <svg width="24" height="10" aria-hidden className="shrink-0">
                <line x1="0" y1="5" x2="24" y2="5" stroke={b.color} strokeWidth={Math.max(1.5, b.width * 1.6)} strokeDasharray={b.dashed ? '4 3' : undefined} />
              </svg>
              <span>{b.label}</span>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-muted">Lower voltages appear as you zoom in</p>
      </>
    );
  },
};

export default lineModule;
