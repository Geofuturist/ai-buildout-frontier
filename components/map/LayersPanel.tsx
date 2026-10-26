'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Info } from 'lucide-react';
import type { ReactNode } from 'react';
import { overlayWord, rowsByTopic } from '@/lib/panel';
import type { PanelRow } from '@/lib/panel';

interface Props {
  rows: PanelRow[];
  /** key of the fill that is on, or null */
  activeFill: string | null;
  overlays: Record<string, boolean>;
  failed: Set<string>;
  /** the Colors switch of a family */
  onColors: (row: PanelRow) => void;
  /** the Points (or Lines) switch of a family */
  onPoints: (row: PanelRow, on: boolean) => void;
  onInfo: (layerId: string) => void;
  /** all topics open from the start (the territory card, where the list is short) */
  openAll?: boolean;
  /** the legend of a family, shown right under its row when something of it is on */
  legendOf?: (row: PanelRow) => ReactNode;
}

export const colorsOn = (r: PanelRow, activeFill: string | null) => activeFill !== null && r.fills.some((i) => i.key === activeFill);
export const pointsOn = (r: PanelRow, overlays: Record<string, boolean>) => r.overlays.some((o) => overlays[o.layer.layer_id]);

function Switch({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} className="flex min-h-[36px] items-center gap-2 pr-3 text-left text-sm text-ink" onClick={onClick}>
      <span aria-hidden className={`relative h-5 w-9 shrink-0 rounded-full border transition-colors ${on ? 'border-[#0f6e6e] bg-[#0f6e6e]' : 'border-[#8a8f96] bg-surface'}`}>
        <span className={`absolute top-[2px] h-3.5 w-3.5 rounded-full transition-all ${on ? 'left-[18px] bg-white' : 'left-[2px] bg-[#8a8f96]'}`} />
      </span>
      {label}
    </button>
  );
}

/**
 * Layers by topic (SPEC_WEB_territory r9 16). One row per source (a family of layers) with at most two switches:
 * Points (or Lines) and Colors. Colors: one family at a time. The legend of a family stands under its row.
 * Nothing is on when the page opens.
 */
export default function LayersPanel({ rows, activeFill, overlays, failed, onColors, onPoints, onInfo, openAll, legendOf }: Props) {
  const topics = rowsByTopic(rows);
  // Compact menu: the topics are buttons, a topic opens its list of layers (all closed at the start)
  const [openTopics, setOpenTopics] = useState<Set<string>>(new Set());
  const isOpenTopic = (t: string) => Boolean(openAll) !== openTopics.has(t);
  const toggle = (t: string) =>
    setOpenTopics((prev) => {
      const n = new Set(prev);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });
  if (topics.length === 0) return <p className="text-xs text-muted">No layers in this release.</p>;

  return (
    <div className="space-y-1">
      {topics.map(({ topic, rows: list }) => {
        const isOpen = isOpenTopic(topic);
        const on = list.filter((r) => colorsOn(r, activeFill) || pointsOn(r, overlays)).length;
        return (
          <section key={topic} aria-label={topic}>
            <button
              type="button"
              className="flex min-h-[40px] w-full items-center justify-between rounded-md border border-line bg-surface px-3 text-left text-sm font-semibold text-ink hover:border-accent"
              aria-expanded={isOpen}
              onClick={() => toggle(topic)}
            >
              <span>
                {topic}
                {on > 0 && <span className="ml-2 rounded-full bg-[#0f6e6e] px-1.5 py-0.5 text-[11px] font-semibold text-white">{on} on</span>}
              </span>
              <span className="flex items-center gap-2 text-xs font-normal text-muted">
                {list.length}
                {isOpen ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
              </span>
            </button>
            {isOpen && (
              <ul className="mb-2 mt-1">
                {list.map((r) => {
                  const bad = r.overlays.some((o) => failed.has(o.layer.layer_id));
                  const legend = legendOf?.(r);
                  return (
                    <li key={r.key} className="border-b border-line py-2 last:border-b-0">
                      <div className="flex items-start gap-1 px-1">
                        <span className="min-w-0 flex-1 leading-tight">
                          <span className="block text-sm text-ink">{r.title}</span>
                          <span className="block text-xs text-ink2">
                            {r.scope}
                            {bad && <strong className="ml-1 text-[#9a2a00]">· Failed to load</strong>}
                          </span>
                          <span className="block text-xs text-muted">{[r.source, r.fresh].filter(Boolean).join(' · ')}</span>
                        </span>
                        <button type="button" className="flex h-9 w-9 shrink-0 items-center justify-center text-accent" aria-label={`About: ${r.infoLayer.title}`} onClick={() => onInfo(r.infoLayer.layer_id)}>
                          <Info size={18} aria-hidden />
                        </button>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 px-1">
                        {r.overlays.length > 0 && <Switch on={pointsOn(r, overlays)} label={overlayWord(r)} onClick={() => onPoints(r, !pointsOn(r, overlays))} />}
                        {r.fills.length > 0 && <Switch on={colorsOn(r, activeFill)} label="Colors" onClick={() => onColors(r)} />}
                      </div>
                      {legend}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
