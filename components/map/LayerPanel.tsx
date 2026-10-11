'use client';

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';
import type { LayerEntry, Meta } from '@/lib/data';
import { throughLabel } from '@/lib/format';
import Legend from './Legend';
import type { MapData } from './types';

const COUNTRY: Record<string, string> = { USA: 'United States', FRA: 'France', NOR: 'Norway', GBR: 'United Kingdom' };
const DOMAIN: Record<string, string> = { energy: 'Energy', dc: 'Data centers', restrictions: 'Restrictions', observability: 'Observability' };
const LEVEL: Record<string, string> = { ADM0: 'Country', ADM1: 'Region', ADM2: 'County', line: 'Segments' };

interface Props {
  data: MapData;
  activeId: string;
  linesOn: Record<string, boolean>;
  failed: Set<string>;
  hidden: boolean;
  onActive: (id: string) => void;
  onLines: (id: string, on: boolean) => void;
  onInfo: (id: string) => void;
  onUS: () => void;
  onWorld: () => void;
}

export default function LayerPanel({ data, activeId, linesOn, failed, hidden, onActive, onLines, onInfo, onUS, onWorld }: Props) {
  const [open, setOpen] = useState(false);

  const layers = data.layers.filter((l) => l.dataset === 'abf-layers');
  const polys = layers.filter((l) => l.tiles.geometry_type === 'polygon' && data.metas[l.meta_id]?.display?.value_field);
  const lines = layers.filter((l) => l.tiles.geometry_type === 'line');

  const groups = useMemo(() => {
    const m = new Map<string, LayerEntry[]>();
    for (const l of polys) {
      const meta = data.metas[l.meta_id];
      const iso = meta.coverage.frame?.iso3 ?? '';
      const key = `${DOMAIN[l.domain] ?? l.domain} · ${COUNTRY[iso] ?? iso}`;
      m.set(key, [...(m.get(key) ?? []), l]);
    }
    return [...m.entries()];
  }, [polys, data.metas]);

  const activeMeta: Meta | null = activeId !== 'none' ? data.metas[layers.find((l) => l.layer_id === activeId)?.meta_id ?? ''] ?? null : null;
  const anyLines = lines.some((l) => linesOn[l.layer_id]);
  const activeTitle = activeMeta ? layers.find((l) => l.layer_id === activeId)?.title : 'No layer';

  const row = (l: LayerEntry, radio: boolean) => {
    const meta = data.metas[l.meta_id];
    const isFailed = failed.has(l.layer_id);
    return (
      <li key={l.layer_id} className="flex items-stretch">
        <label className="flex min-h-[44px] flex-1 cursor-pointer items-center gap-2 py-1">
          {radio ? (
            <input type="radio" name="adm-layer" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={activeId === l.layer_id} onChange={() => onActive(l.layer_id)} />
          ) : (
            <input type="checkbox" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={Boolean(linesOn[l.layer_id])} onChange={(e) => onLines(l.layer_id, e.target.checked)} />
          )}
          <span className="leading-tight">
            <span className="block text-sm text-ink">{l.title}</span>
            <span className="block text-xs text-muted">
              {LEVEL[l.level] ?? l.level} · {throughLabel(meta)}
              {isFailed && <strong className="ml-1 text-[#9a2a00]">· Failed to load</strong>}
            </span>
          </span>
        </label>
        <button
          type="button"
          className="flex h-11 w-11 shrink-0 items-center justify-center text-accent"
          aria-label={`About: ${l.title}`}
          onClick={() => onInfo(l.layer_id)}
        >
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
      <button
        type="button"
        className="flex min-h-[48px] items-center justify-between px-3 text-left md:hidden"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-sm">
          <span className="font-semibold">Layers</span> <span className="text-ink2">· {activeTitle}</span>
        </span>
        {open ? <ChevronDown size={20} aria-hidden /> : <ChevronUp size={20} aria-hidden />}
      </button>

      <div className={`${open ? 'block' : 'hidden'} overflow-y-auto px-3 pb-3 md:block md:pt-3`}>
        <h2 className="hidden text-base font-semibold md:block">Layers</h2>

        {groups.map(([title, ls]) => (
          <div key={title} className="mt-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
            <ul>
              {ls.map((l) => row(l, true))}
              <li className="flex items-stretch">
                <label className="flex min-h-[44px] flex-1 cursor-pointer items-center gap-2 py-1">
                  <input type="radio" name="adm-layer" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={activeId === 'none'} onChange={() => onActive('none')} />
                  <span className="text-sm text-ink">None</span>
                </label>
              </li>
            </ul>
          </div>
        ))}

        {lines.length > 0 && (
          <div className="mt-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Overlays</h3>
            <ul>{lines.map((l) => row(l, false))}</ul>
          </div>
        )}

        <div className="mt-2 flex gap-2">
          <button type="button" className="btn flex-1" onClick={onUS}>United States</button>
          <button type="button" className="btn flex-1" onClick={onWorld}>World</button>
        </div>

        <hr className="my-3 border-line" />
        <Legend meta={activeMeta} showLines={anyLines} />
      </div>
    </aside>
  );
}
