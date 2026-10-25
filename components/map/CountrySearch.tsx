'use client';

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { searchRows } from '@/lib/panel';
import type { PanelRow } from '@/lib/panel';
import type { MapData } from './types';

type Country = MapData['countries'][number];

/**
 * Search of a country by name (all countries of the boundaries, also the small ones) and of a layer by its title, source,
 * topic, scope or tags. A country is selected and the map flies to it; a layer is switched on.
 */
export default function CountrySearch({ countries, rows, onPick, onLayer }: { countries: Country[]; rows: PanelRow[]; onPick: (c: Country) => void; onLayer: (r: PanelRow) => void }) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const found = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    const starts = countries.filter((c) => c.name.toLowerCase().startsWith(t));
    const inside = countries.filter((c) => !c.name.toLowerCase().startsWith(t) && c.name.toLowerCase().includes(t));
    return [...starts, ...inside].slice(0, 6);
  }, [q, countries]);
  const layers = useMemo(() => searchRows(rows, q), [rows, q]);
  const total = found.length + layers.length;

  const pick = (i: number) => {
    setQ('');
    setActive(0);
    if (i < found.length) onPick(found[i]);
    else onLayer(layers[i - found.length]);
  };

  return (
    <div className="relative mb-3">
      <label className="sr-only" htmlFor="country-search">Find a country or a layer</label>
      <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-2">
        <Search size={16} aria-hidden className="shrink-0 text-muted" />
        <input
          id="country-search"
          type="search"
          autoComplete="off"
          placeholder="Find a country or a layer"
          className="h-9 w-full bg-transparent text-sm outline-none"
          role="combobox"
          aria-expanded={total > 0}
          aria-controls="country-search-list"
          aria-autocomplete="list"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown' && total) {
              e.preventDefault();
              setActive((a) => (a + 1) % total);
            } else if (e.key === 'ArrowUp' && total) {
              e.preventDefault();
              setActive((a) => (a + total - 1) % total);
            } else if (e.key === 'Enter' && active < total) {
              e.preventDefault();
              pick(active);
            } else if (e.key === 'Escape') setQ('');
          }}
        />
      </div>
      {q.trim() && total === 0 && <p className="mt-1 text-xs text-muted">No country or layer found.</p>}
      {total > 0 && (
        <ul id="country-search-list" role="listbox" className="absolute inset-x-0 z-30 mt-1 max-h-72 overflow-y-auto rounded-md border border-line bg-surface shadow-lg">
          {found.map((c, i) => (
            <li key={c.iso3} role="option" aria-selected={i === active}>
              <button type="button" className={`flex min-h-[40px] w-full items-center justify-between px-3 text-left text-sm hover:bg-[#eef3f3] ${i === active ? 'bg-[#eef3f3]' : ''}`} onClick={() => pick(i)}>
                <span>{c.name}</span>
                <span className="text-xs text-muted">{c.iso3}</span>
              </button>
            </li>
          ))}
          {layers.map((r, j) => {
            const i = found.length + j;
            return (
              <li key={r.key} role="option" aria-selected={i === active}>
                <button type="button" className={`block min-h-[40px] w-full px-3 py-1.5 text-left hover:bg-[#eef3f3] ${i === active ? 'bg-[#eef3f3]' : ''}`} onClick={() => pick(i)}>
                  <span className="block text-sm leading-tight">{r.title}</span>
                  <span className="block text-xs text-ink2">Layer · {r.scope} · {r.topic}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
