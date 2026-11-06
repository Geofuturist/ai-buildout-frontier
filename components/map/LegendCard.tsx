'use client';

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import Link from 'next/link';
import { ChevronLeft, ChevronRight, ListTree } from 'lucide-react';
import type { PanelRow } from '@/lib/panel';
import { COLORS } from '@/lib/style';
import CountrySearch from './CountrySearch';
import LayersPanel from './LayersPanel';
import type { MapData } from './types';

const FOLD_KEY = 'abf.panel.folded';

interface Props {
  data: MapData;
  rows: PanelRow[];
  onSearch: (c: MapData['countries'][number]) => void;
  /** all rows (also of single countries) for the search by layer */
  allRows: PanelRow[];
  legendOf: (row: PanelRow) => ReactNode;
  onFound: (r: PanelRow) => void;
  activeFill: string | null;
  overlays: Record<string, boolean>;
  failed: Set<string>;
  onColors: (row: PanelRow) => void;
  onPoints: (row: PanelRow, on: boolean) => void;
  onInfo: (layerId: string) => void;
  /** a card of the right-hand side is open: on a phone the legend steps aside */
  covered: boolean;
  /** changes when a territory is chosen: the phone list closes so the card is not covered */
  nonce: number;
}

/**
 * Legend card, left (SPEC_WEB_territory 3). Desktop: top left, folds to the left with a remembered choice.
 * Phone: a small button bottom left that opens the card above the territory bar.
 */
export default function LegendCard({ data, covered, rows, activeFill, overlays, failed, onColors, onPoints, onInfo, onSearch, allRows, legendOf, onFound, nonce }: Props) {
  const [folded, setFolded] = useState(false);
  const [openPhone, setOpenPhone] = useState(false);
  useEffect(() => {
    try {
      if (window.localStorage.getItem(FOLD_KEY) === '1') setFolded(true);
    } catch {
      /* storage may be blocked: the card simply starts open */
    }
  }, []);
  useEffect(() => {
    setOpenPhone(false);
  }, [nonce]);
  const fold = (v: boolean) => {
    setFolded(v);
    try {
      window.localStorage.setItem(FOLD_KEY, v ? '1' : '0');
    } catch {
      /* ignore */
    }
  };

  const body = (
    <div className="flex min-h-0 flex-1 flex-col">
      <CountrySearch countries={data.countries} rows={allRows} onPick={onSearch} onLayer={onFound} />
      {/* The key of the grey countries stays whatever is chosen */}
      <p className="mb-3 flex items-center gap-2 text-xs text-ink2">
        <span className="inline-block h-3 w-5 shrink-0 rounded-sm border border-line" style={{ background: COLORS.dataCountry, opacity: 0.5 }} aria-hidden />
        Grey countries have their own layers. Click one on the map.
      </p>
      <div className="md:min-h-0 md:flex-1 md:overflow-y-auto">
        <LayersPanel rows={rows} activeFill={activeFill} overlays={overlays} failed={failed} onColors={onColors} onPoints={onPoints} onInfo={onInfo} legendOf={legendOf} />
      </div>
      <>
          <p className="mt-3 text-xs text-muted">Layers are named after their source.</p>
          <p className="mt-1 text-xs text-muted">Boundaries follow the US government&apos;s point of view and do not express a position of the project.</p>
      </>
    </div>
  );

  return (
    <>
      {/* Desktop */}
      {folded ? (
        <button
          type="button"
          className="absolute left-3 top-3 z-10 hidden h-9 items-center gap-1 rounded-md border border-line bg-surface pl-2 pr-3 text-[13px] font-semibold text-ink shadow-md hover:text-accent md:flex"
          aria-label="Show the layers"
          aria-expanded={false}
          onClick={() => fold(false)}
        >
          <ChevronRight size={18} aria-hidden />
          Layers
        </button>
      ) : (
        <aside className="absolute left-3 top-3 z-10 hidden max-h-[calc(100%-1.5rem)] w-80 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-lg md:flex" aria-label="Layers and legend">
          <div className="flex items-center justify-between gap-2 px-3 pt-3">
            <Link href="/" className="text-base font-semibold text-ink no-underline">AI Buildout Frontier</Link>
            <button type="button" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line text-ink2 hover:text-accent" aria-label="Hide the layers" aria-expanded onClick={() => fold(true)}>
              <ChevronLeft size={18} aria-hidden />
            </button>
          </div>
          <div className="flex min-h-0 flex-1 flex-col px-3 pb-3 pt-2">{body}</div>
        </aside>
      )}

      {/* Phone */}
      {!covered && (
        <div className="absolute bottom-14 left-3 z-10 md:hidden">
          {openPhone && <aside className="mb-2 max-h-[45vh] w-[min(18rem,calc(100vw-1.5rem))] overflow-y-auto rounded-xl border border-line bg-surface p-3 shadow-lg" aria-label="Layers and legend">{body}</aside>}
          <button
            type="button"
            className="flex h-9 items-center gap-1.5 rounded-md border border-line bg-surface px-3 text-[13px] font-semibold text-ink shadow-md"
            aria-expanded={openPhone}
            onClick={() => setOpenPhone((v) => !v)}
          >
            <ListTree size={16} aria-hidden />
            Layers
          </button>
        </div>
      )}
    </>
  );
}
