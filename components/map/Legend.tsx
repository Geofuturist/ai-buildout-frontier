import type { LayerEntry } from '@/lib/data';
import { MODULES } from './modules';
import type { MapData } from './types';

/** Legend: one block per geometry module, for the layers of that type that are on. */
export default function Legend({ layers, metas, typeFilter, onTypeFilter }: { layers: LayerEntry[]; metas: MapData['metas']; typeFilter?: string | null; onTypeFilter?: (group: string | null) => void }) {
  return (
    <section aria-label="Legend" className="text-sm">
      {MODULES.map((m) => {
        const Block = m.Legend;
        return <Block key={m.type} layers={layers.filter((l) => l.tiles.geometry_type === m.type)} metas={metas} typeFilter={typeFilter} onTypeFilter={onTypeFilter} />;
      })}
      <p className="mt-3 text-xs text-muted">Layers are named after their source.</p>
      <p className="mt-1 text-xs text-muted">
        Boundaries follow the US government&apos;s point of view and do not express a position of the project.
      </p>
    </section>
  );
}
