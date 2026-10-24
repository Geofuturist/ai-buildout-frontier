'use client';

// Card of the whole world (a click on the globe far out): the full files of the layers that cover several countries.
import { ChevronRight, X } from 'lucide-react';
import type { LayerEntry } from '@/lib/data';
import type { CountryModel } from '@/lib/indicators';
import { Downloads } from './parts';

export default function WorldCard({ world, hidden, onClose }: { world: CountryModel | null; hidden: boolean; onClose: () => void }) {
  const layers: LayerEntry[] = world ? world.indicators.flatMap((x) => x.levels.map((lv) => lv.layer)).concat(world.overlays) : [];
  return (
    <aside
      className={`absolute inset-x-0 bottom-0 z-20 flex max-h-[58%] flex-col rounded-t-xl border border-line bg-surface shadow-lg md:inset-x-auto md:bottom-auto md:right-3 md:top-14 md:max-h-[calc(100%-12rem)] md:w-[24rem] md:rounded-xl ${hidden ? 'hidden' : ''}`}
      aria-label="World"
    >
      <button type="button" className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-md border border-line text-ink2 hover:text-accent" aria-label="Close the world card" onClick={onClose}>
        <X size={18} aria-hidden />
      </button>
      <div className="overflow-y-auto px-4 pb-4 pt-3 text-sm md:pr-12">
        <h2 className="text-base font-semibold leading-tight">World</h2>
        <p className="text-xs text-muted">Layers that cover several countries</p>
        {layers.length === 0 && <p className="mt-3 text-ink2">No layers of the whole world in this release.</p>}
        {layers.length > 0 && <p className="mt-3 text-sm font-semibold">Download for the world</p>}
        {layers.map((layer) => (
          <div key={layer.layer_id} className="mt-2">
            <p className="text-xs text-ink2">{layer.title}</p>
            <Downloads layer={layer} />
          </div>
        ))}
        <p className="mt-3 flex items-center gap-1 text-xs text-ink2">
          Zoom in and click a country for its own layers <ChevronRight size={14} aria-hidden />
        </p>
      </div>
    </aside>
  );
}
