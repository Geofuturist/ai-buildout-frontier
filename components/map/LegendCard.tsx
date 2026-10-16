'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ChevronLeft, ChevronRight, ListTree } from 'lucide-react';
import type { LayerEntry } from '@/lib/data';
import type { CountryModel } from '@/lib/indicators';
import { COLORS } from '@/lib/style';
import Legend from './Legend';
import type { MapData } from './types';

const FOLD_KEY = 'abf.panel.folded';

interface Props {
  data: MapData;
  /** title of the active indicator with the level that is drawn, or null when no country is chosen */
  heading: string | null;
  /** the fill layer and the switched-on points and lines */
  layers: LayerEntry[];
  /** shown under the heading when the indicator has no data at the level that is drawn */
  note: string | null;
  /** countries with data (start globe: shaded; also listed here as buttons) */
  countries: CountryModel[];
  onCountry: (iso3: string) => void;
  /** a card of the right-hand side is open: on a phone the legend steps aside */
  covered: boolean;
}

/**
 * Legend card, left (SPEC_WEB_territory 3). Desktop: top left, folds to the left with a remembered choice.
 * Phone: a small button bottom left that opens the card above the territory bar.
 */
export default function LegendCard({ data, heading, note, layers, covered, countries, onCountry }: Props) {
  const [folded, setFolded] = useState(false);
  const [openPhone, setOpenPhone] = useState(false);
  useEffect(() => {
    try {
      if (window.localStorage.getItem(FOLD_KEY) === '1') setFolded(true);
    } catch {
      /* storage may be blocked: the card simply starts open */
    }
  }, []);
  const fold = (v: boolean) => {
    setFolded(v);
    try {
      window.localStorage.setItem(FOLD_KEY, v ? '1' : '0');
    } catch {
      /* ignore */
    }
  };

  const body = (
    <>
      {heading ? (
        <p className="mb-2 text-sm font-semibold leading-tight text-ink">{heading}</p>
      ) : (
        <>
          <p className="mb-1 flex items-center gap-2 text-sm text-ink2">
            <span className="inline-block h-3 w-5 shrink-0 rounded-sm border border-line" style={{ background: COLORS.dataCountry, opacity: 0.5 }} aria-hidden />
            Countries with data. Click one on the map.
          </p>
          <p className="text-xs text-muted">
            {countries.map((c, i) => (
              <span key={c.iso3}>
                {i > 0 && ' · '}
                <button type="button" className="text-accent hover:underline" onClick={() => onCountry(c.iso3)}>{c.name}</button>
              </span>
            ))}
          </p>
        </>
      )}
      {note && <p className="mb-2 rounded-md border border-dashed border-[#8a8f96] p-2 text-xs text-ink2">{note}</p>}
      {heading && <Legend layers={layers} metas={data.metas} />}
      {!heading && (
        <>
          <p className="mt-3 text-xs text-muted">Layers are named after their source.</p>
          <p className="mt-1 text-xs text-muted">Boundaries follow the US government&apos;s point of view and do not express a position of the project.</p>
        </>
      )}
    </>
  );

  return (
    <>
      {/* Desktop */}
      {folded ? (
        <button
          type="button"
          className="absolute left-3 top-3 z-10 hidden h-9 items-center gap-1 rounded-md border border-line bg-surface pl-2 pr-3 text-[13px] font-semibold text-ink shadow-md hover:text-accent md:flex"
          aria-label="Show the legend"
          aria-expanded={false}
          onClick={() => fold(false)}
        >
          <ChevronRight size={18} aria-hidden />
          Legend
        </button>
      ) : (
        <aside className="absolute left-3 top-3 z-10 hidden max-h-[calc(100%-1.5rem)] w-72 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-lg md:flex" aria-label="Legend">
          <div className="flex items-center justify-between gap-2 px-3 pt-3">
            <Link href="/" className="text-base font-semibold text-ink no-underline">AI Buildout Frontier</Link>
            <button type="button" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line text-ink2 hover:text-accent" aria-label="Hide the legend" aria-expanded onClick={() => fold(true)}>
              <ChevronLeft size={18} aria-hidden />
            </button>
          </div>
          <div className="overflow-y-auto px-3 pb-3 pt-2">{body}</div>
        </aside>
      )}

      {/* Phone */}
      {!covered && (
        <div className="absolute bottom-14 left-3 z-10 md:hidden">
          {openPhone && <aside className="mb-2 max-h-[45vh] w-[min(18rem,calc(100vw-1.5rem))] overflow-y-auto rounded-xl border border-line bg-surface p-3 shadow-lg" aria-label="Legend">{body}</aside>}
          <button
            type="button"
            className="flex h-9 items-center gap-1.5 rounded-md border border-line bg-surface px-3 text-[13px] font-semibold text-ink shadow-md"
            aria-expanded={openPhone}
            onClick={() => setOpenPhone((v) => !v)}
          >
            <ListTree size={16} aria-hidden />
            Legend
          </button>
        </div>
      )}
    </>
  );
}
