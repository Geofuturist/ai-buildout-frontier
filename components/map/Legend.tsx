import type { LayerEntry } from '@/lib/data';
import { MODULES } from './modules';
import type { LayerFilters } from '@/lib/filters';
import { KINDS } from '@/lib/icons';
import { kindsOf, shapeOf } from '@/lib/pointStatus';
import { Mark } from './modules/symbols';
import type { MapData } from './types';

/** Legend: one block per geometry module, for the layers of that type that are on. */
export default function Legend({ layers, metas, typeFilter, onTypeFilter, layerFilters, onLayerFilter }: { layers: LayerEntry[]; metas: MapData['metas']; typeFilter?: string | null; onTypeFilter?: (group: string | null) => void; layerFilters?: LayerFilters; onLayerFilter?: (layerId: string, field: string, values: string[]) => void }) {
  // One block "Status": the kinds of icon that the layers on the map use, with the words of content/site.json
  const withStatus = layers.map((l) => metas[l.meta_id]?.display).filter((d) => d?.status_style);
  const kinds = KINDS.filter((k) => withStatus.some((d) => kindsOf(d).includes(k)));
  const labels = withStatus[0]?.status_style?.labels ?? {};
  const shape = shapeOf(withStatus[0]) ?? 'circle';
  return (
    <section aria-label="Legend" className="text-sm">
      {MODULES.map((m) => {
        const Block = m.Legend;
        return <Block key={m.type} layers={layers.filter((l) => l.tiles.geometry_type === m.type)} metas={metas} typeFilter={typeFilter} onTypeFilter={onTypeFilter} layerFilters={layerFilters} onLayerFilter={onLayerFilter} />;
      })}
      {kinds.length > 0 && (
        <div className="mt-3 border-t border-line pt-2">
          <h3 className="mb-1 text-[13px] font-semibold text-ink">Status</h3>
          <ul className="space-y-0">
            {kinds.map((k) => (
              <li key={k} className="flex items-center gap-2"><Mark shape={shape} kind={k} color="#6b6f76" r={6} /><span>{labels[k] ?? k}</span></li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
