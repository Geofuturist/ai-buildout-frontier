'use client';

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';
import type { LayerEntry } from '@/lib/data';
import { capitalize, domainLabel, groupByCountry, unionBbox, unitWord } from '@/lib/layers';
import { throughLabel } from '@/lib/format';
import Legend from './Legend';
import { MODULE_BY_TYPE } from './modules';
import { selectDataLayers } from './select';
import type { MapData } from './types';

interface Props {
  data: MapData;
  activeId: string;
  overlays: Record<string, boolean>;
  failed: Set<string>;
  hidden: boolean;
  onActive: (id: string) => void;
  onOverlay: (id: string, on: boolean) => void;
  onInfo: (id: string) => void;
  onZoom: (bbox: [number, number, number, number]) => void;
  onWorld: () => void;
}

export default function LayerPanel({ data, activeId, overlays, failed, hidden, onActive, onOverlay, onInfo, onZoom, onWorld }: Props) {
  const [open, setOpen] = useState(false);

  const layers = useMemo(() => selectDataLayers(data), [data]);
  const countries = useMemo(() => groupByCountry(layers, data.metas), [layers, data.metas]);
  const exclusive = (l: LayerEntry) => MODULE_BY_TYPE[l.tiles.geometry_type].exclusive;

  const activeLayer = layers.find((l) => l.layer_id === activeId);
  const switchedOn = layers.filter((l) => (exclusive(l) ? l.layer_id === activeId : overlays[l.layer_id]));
  const activeTitle = activeLayer ? activeLayer.title : 'No layer';

  const row = (l: LayerEntry) => {
    const meta = data.metas[l.meta_id];
    const isFailed = failed.has(l.layer_id);
    const radio = exclusive(l);
    return (
      <li key={l.layer_id} className="flex items-stretch">
        <label className="flex min-h-[44px] flex-1 cursor-pointer items-center gap-2 py-1">
          {radio ? (
            <input type="radio" name="adm-layer" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={activeId === l.layer_id} onChange={() => onActive(l.layer_id)} />
          ) : (
            <input type="checkbox" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={Boolean(overlays[l.layer_id])} onChange={(e) => onOverlay(l.layer_id, e.target.checked)} />
          )}
          <span className="leading-tight">
            <span className="block text-sm text-ink">{l.title}</span>
            <span className="block text-xs text-muted">
              {capitalize(unitWord(l))} · {throughLabel(meta)}
              {isFailed && <strong className="ml-1 text-[#9a2a00]">· Failed to load</strong>}
            </span>
          </span>
        </label>
        <button type="button" className="flex h-11 w-11 shrink-0 items-center justify-center text-accent" aria-label={`About: ${l.title}`} onClick={() => onInfo(l.layer_id)}>
          <Info size={18} aria-hidden />
        </button>
      </li>
    );
  };

  return (
    <aside
      className={`absolute inset-x-0 bottom-0 z-10 flex max-h-[62%] flex-col rounded-t-xl border border-line bg-surface shadow-lg md:inset-x-auto md:bottom-auto md:left-3 md:top-3 md:max-h-[calc(100%-1.5rem)] md:w-80 md:rounded-xl ${hidden ? 'max-md:hidden' : ''}`}
      aria-label="Layers"
    >
      <button type="button" className="flex min-h-[48px] items-center justify-between px-3 text-left md:hidden" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="text-sm">
          <span className="font-semibold">Layers</span> <span className="text-ink2">· {activeTitle}</span>
        </span>
        {open ? <ChevronDown size={20} aria-hidden /> : <ChevronUp size={20} aria-hidden />}
      </button>

      <div className={`${open ? 'block' : 'hidden'} overflow-y-auto px-3 pb-3 md:block md:pt-3`}>
        <h2 className="hidden text-base font-semibold md:block">Layers</h2>

        {countries.map((c) => (
          <div key={c.iso3} className="mt-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{c.name}</h3>
            {c.domains.map((d) => (
              <div key={d.domain} className="mt-1">
                {c.domains.length > 1 && <p className="text-xs text-ink2">{domainLabel(d.domain)}</p>}
                <ul>{[...d.layers.filter(exclusive), ...d.layers.filter((l) => !exclusive(l))].map(row)}</ul>
              </div>
            ))}
          </div>
        ))}

        <label className="mt-1 flex min-h-[44px] cursor-pointer items-center gap-2 py-1">
          <input type="radio" name="adm-layer" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={activeId === 'none'} onChange={() => onActive('none')} />
          <span className="text-sm text-ink">None</span>
        </label>

        <div className="mt-2 flex flex-wrap gap-2">
          {countries.map((c) => {
            const bbox = unionBbox(c.domains.flatMap((d) => d.layers));
            return bbox ? (
              <button key={c.iso3} type="button" className="btn flex-1" onClick={() => onZoom(bbox)}>{c.name}</button>
            ) : null;
          })}
          <button type="button" className="btn flex-1" onClick={onWorld}>World</button>
        </div>

        <hr className="my-3 border-line" />
        <Legend layers={switchedOn} metas={data.metas} />
      </div>
    </aside>
  );
}
