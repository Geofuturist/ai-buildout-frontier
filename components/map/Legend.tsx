import type { LayerEntry } from '@/lib/data';
import { MODULES } from './modules';
import type { LayerFilters } from '@/lib/filters';
import { KINDS } from '@/lib/icons';
import { kindsOf, shapeOf } from '@/lib/pointStatus';
import { Mark } from './modules/symbols';
import type { MapData } from './types';

/** Legend: one block per geometry module, for the layers of that type that are on. */
export default function Legend({ layers, metas, typeFilter, onTypeFilter, layerFilters, onLayerFilter, statusLegend }: { statusLegend?: MapData['status_legend']; layers: LayerEntry[]; metas: MapData['metas']; typeFilter?: string | null; onTypeFilter?: (group: string | null) => void; layerFilters?: LayerFilters; onLayerFilter?: (layerId: string, field: string, values: string[]) => void }) {
  // One block "Status": the kinds of icon that the layers on the map use, with the words of content/site.json
  const withStatus = layers.map((l) => metas[l.meta_id]?.display).filter((d) => d?.status_style);
  const kinds = KINDS.filter((k) => withStatus.some((d) => kindsOf(d).includes(k)));
  const labels = withStatus[0]?.status_style?.labels ?? {};
  const shape = shapeOf(withStatus[0]) ?? 'circle';
  const ids = new Set(layers.map((l) => l.layer_id));
  const lines = (statusLegend?.lines ?? []).filter((x) => x.layers.some((id) => ids.has(id)) && (!x.kind || kinds.includes(x.kind as (typeof KINDS)[number])));
  return (
    <section aria-label="Legend" className="text-sm">
      {MODULES.map((m) => {
        const Block = m.Legend;
        return <Block key={m.type} layers={layers.filter((l) => l.tiles.geometry_type === m.type)} metas={metas} typeFilter={typeFilter} onTypeFilter={onTypeFilter} layerFilters={layerFilters} onLayerFilter={onLayerFilter} />;
      })}
      {kinds.length > 0 && (
        <div className="mt-3 border-t border-line pt-2">
          <h3 className="mb-1 text-[13px] font-semibold text-ink">{statusLegend?.title || 'Status'}</h3>
          <ul className="space-y-0">
            {kinds.map((k) => (
              <li key={k} className="flex items-center gap-2"><Mark shape={shape} kind={k} color="#6b6f76" r={6} /><span>{labels[k] ?? k}</span></li>
            ))}
          </ul>
          {lines.length > 0 && (
            <div className="mt-2 space-y-1 text-xs text-ink2">
              {statusLegend?.note && <p>{statusLegend.note}</p>}
              {lines.map((x, i) => x.kind
                ? <p key={i} className="flex items-center gap-2"><Mark shape={shape} kind={x.kind as (typeof KINDS)[number]} color="#6b6f76" r={6} /><span>{x.text}</span></p>
                : <p key={i}>{x.text}</p>)}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
