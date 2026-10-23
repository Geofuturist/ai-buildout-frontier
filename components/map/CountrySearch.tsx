'use client';

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import type { MapData } from './types';

type Country = MapData['countries'][number];

/** Search of a country by name (all countries of the boundaries, also the small ones). Choosing one selects it and flies to it. */
export default function CountrySearch({ countries, onPick }: { countries: Country[]; onPick: (c: Country) => void }) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const found = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    const starts = countries.filter((c) => c.name.toLowerCase().startsWith(t));
    const inside = countries.filter((c) => !c.name.toLowerCase().startsWith(t) && c.name.toLowerCase().includes(t));
    return [...starts, ...inside].slice(0, 8);
  }, [q, countries]);

  const pick = (c: Country) => {
    setQ('');
    setActive(0);
    onPick(c);
  };

  return (
    <div className="relative mb-3">
      <label className="sr-only" htmlFor="country-search">Find a country</label>
      <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-2">
        <Search size={16} aria-hidden className="shrink-0 text-muted" />
        <input
          id="country-search"
          type="search"
          autoComplete="off"
          placeholder="Find a country"
          className="h-9 w-full bg-transparent text-sm outline-none"
          role="combobox"
          aria-expanded={found.length > 0}
          aria-controls="country-search-list"
          aria-autocomplete="list"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown' && found.length) {
              e.preventDefault();
              setActive((a) => (a + 1) % found.length);
            } else if (e.key === 'ArrowUp' && found.length) {
              e.preventDefault();
              setActive((a) => (a + found.length - 1) % found.length);
            } else if (e.key === 'Enter' && found[active]) {
              e.preventDefault();
              pick(found[active]);
            } else if (e.key === 'Escape') setQ('');
          }}
        />
      </div>
      {q.trim() && found.length === 0 && <p className="mt-1 text-xs text-muted">No country with this name.</p>}
      {found.length > 0 && (
        <ul id="country-search-list" role="listbox" className="absolute inset-x-0 z-30 mt-1 max-h-64 overflow-y-auto rounded-md border border-line bg-surface shadow-lg">
          {found.map((c, i) => (
            <li key={c.iso3} role="option" aria-selected={i === active}>
              <button type="button" className={`flex min-h-[40px] w-full items-center justify-between px-3 text-left text-sm hover:bg-[#eef3f3] ${i === active ? 'bg-[#eef3f3]' : ''}`} onClick={() => pick(c)}>
                <span>{c.name}</span>
                <span className="text-xs text-muted">{c.iso3}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
