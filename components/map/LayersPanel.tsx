'use client';

import { Info } from 'lucide-react';
import { rowsByTopic } from '@/lib/panel';
import type { PanelRow } from '@/lib/panel';

interface Props {
  rows: PanelRow[];
  /** key of the indicator whose fill is on, or null */
  activeFill: string | null;
  overlays: Record<string, boolean>;
  failed: Set<string>;
  onFill: (row: PanelRow) => void;
  onOverlay: (row: PanelRow, on: boolean) => void;
  onInfo: (layerId: string) => void;
}

/**
 * Layers by topic (SPEC_WEB_territory r4 12). Fills are switches (one fill on the map at a time), points and
 * lines are checkboxes. Nothing is on when the page opens.
 */
export default function LayersPanel({ rows, activeFill, overlays, failed, onFill, onOverlay, onInfo }: Props) {
  const topics = rowsByTopic(rows);
  if (topics.length === 0) return <p className="text-xs text-muted">No layers in this release.</p>;

  const text = (r: PanelRow, bad: boolean) => (
    <span className="min-w-0 leading-tight">
      <span className="block text-sm text-ink">{r.title}</span>
      <span className="block text-xs text-ink2">
        {r.scope} · {r.levels}
        {bad && <strong className="ml-1 text-[#9a2a00]">· Failed to load</strong>}
      </span>
      <span className="block text-xs text-muted">{[r.source, r.fresh].filter(Boolean).join(' · ')}</span>
    </span>
  );

  return (
    <div className="space-y-3">
      {topics.map(({ topic, rows: list }) => (
        <section key={topic} aria-label={topic}>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{topic}</h3>
          <ul>
            {list.map((r) => (
              <li key={r.key} className="flex items-stretch">
                {r.kind === 'fill' ? (
                  <button
                    type="button"
                    role="switch"
                    aria-checked={activeFill === r.key}
                    className="flex min-h-[44px] flex-1 items-center gap-2 py-1 text-left"
                    onClick={() => onFill(r)}
                  >
                    <span aria-hidden className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors ${activeFill === r.key ? 'border-[#0f6e6e] bg-[#0f6e6e]' : 'border-[#8a8f96] bg-surface'}`}>
                      <span className={`absolute top-[2px] h-3.5 w-3.5 rounded-full transition-all ${activeFill === r.key ? 'left-[18px] bg-white' : 'left-[2px] bg-[#8a8f96]'}`} />
                    </span>
                    {text(r, false)}
                  </button>
                ) : (
                  <label className="flex min-h-[44px] flex-1 cursor-pointer items-center gap-2 py-1">
                    <input type="checkbox" className="h-4 w-4 shrink-0 accent-[#0f6e6e] ml-[10px] mr-[10px]" checked={Boolean(overlays[r.key])} onChange={(e) => onOverlay(r, e.target.checked)} />
                    {text(r, failed.has(r.key))}
                  </label>
                )}
                <button type="button" className="flex h-11 w-11 shrink-0 items-center justify-center text-accent" aria-label={`About: ${r.infoLayer.title}`} onClick={() => onInfo(r.infoLayer.layer_id)}>
                  <Info size={18} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
