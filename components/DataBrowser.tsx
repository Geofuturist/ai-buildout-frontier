'use client';

// The Data page (SPEC_WEB_territory 15): two views, "By topic" and "By country"; a card for each indicator, closed by default.
// The view and the country are in the address (/data/?view=country&c=FRA); a link to one layer (/data/#<layer_id>)
// opens the card that holds it.
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';
import CopyButton from '@/components/CopyButton';
import { anchorOfTopic, countriesOf, topicsOf, zenodoLinks } from '@/lib/dataCards';
import type { DataCard } from '@/lib/dataCards';
import { formatBytes } from '@/lib/format';
import { WORLD } from '@/lib/layers';

type View = 'topic' | 'country';

function Card({ card, open, onToggle, worldNote }: { card: DataCard; open: boolean; onToggle: () => void; worldNote: boolean }) {
  return (
    <article id={`card-${card.key}`} className="my-4 rounded-lg border border-line bg-surface p-4">
      {card.parts.map((p) => <span key={p.layerId} id={p.layerId} />)}
      <h3 className="text-base font-semibold leading-snug">{card.title}</h3>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-0.5 text-sm sm:grid-cols-[8rem_1fr]">
        <dt className="text-muted">Coverage</dt>
        <dd>{card.scope}{worldNote && card.iso3 === WORLD ? ' · full files, not cut by country' : ''}</dd>
        <dt className="text-muted">Levels</dt>
        <dd>{card.levels}</dd>
        <dt className="text-muted">Source</dt>
        <dd>{card.source}</dd>
        <dt className="text-muted">Data</dt>
        <dd>{card.through}</dd>
        <dt className="text-muted">License</dt>
        <dd><a href={card.license.url}>{card.license.name}</a></dd>
        <dt className="text-muted">Dataset</dt>
        <dd>{card.dataset.name} v{card.dataset.version} · {card.dataset.doiUrl ? <a href={card.dataset.doiUrl}>{card.dataset.doi}</a> : 'DOI not assigned'}</dd>
      </dl>
      <button type="button" className="btn mt-3 w-full justify-between sm:w-auto" aria-expanded={open} aria-controls={`files-${card.key}`} onClick={onToggle}>
        <span className="flex items-center"><Download size={16} aria-hidden className="mr-1.5" />Files</span>
        {open ? <ChevronUp size={16} aria-hidden className="ml-3" /> : <ChevronDown size={16} aria-hidden className="ml-3" />}
      </button>
      <div id={`files-${card.key}`} hidden={!open} className="mt-3">
        {card.parts.map((p) => (
          <div key={p.layerId} className="mt-2">
            {card.parts.length > 1 && <p className="text-sm font-semibold">{p.title}</p>}
            <ul className="mt-1 flex flex-wrap gap-2">
              {p.files.map((f) => (
                <li key={f.url}>
                  <a className="btn" href={f.url} rel="noopener" title={`SHA-256 ${f.sha256}`}>
                    {f.label} <span className="font-normal text-muted">{formatBytes(f.bytes)}</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {card.extra.length > 0 && (
          <div className="mt-3">
            <p className="text-sm font-semibold">Reference files</p>
            <ul className="mt-1 space-y-0.5 text-sm">
              {card.extra.map((f) => (
                <li key={f.url}><a href={f.url}>{f.name}</a> <span className="text-muted">· {f.label} · {formatBytes(f.bytes)}</span></li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <CopyButton text={card.citation} label="Cite" />
          {card.anchor && <Link href={`/methodology/#${card.anchor}`}>Methodology →</Link>}
        </div>
      </div>
    </article>
  );
}

function ZenodoLinks({ cards }: { cards: DataCard[] }) {
  const links = zenodoLinks(cards);
  if (links.length === 0) return null;
  return (
    <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
      {links.map((l) => (
        <a key={l.name} href={l.url}>All files of {l.name} {l.version} (Zenodo) →</a>
      ))}
    </p>
  );
}

export default function DataBrowser({ cards }: { cards: DataCard[] }) {
  const topics = useMemo(() => topicsOf(cards), [cards]);
  const countries = useMemo(() => countriesOf(cards), [cards]);
  const [view, setView] = useState<View>('topic');
  const [iso, setIso] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set());

  // Start from the address: ?view=country&c=FRA, or a hash that names a layer
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    let v: View = sp.get('view') === 'country' ? 'country' : 'topic';
    let c = sp.get('c');
    const hash = decodeURIComponent(window.location.hash.replace(/^#/, ''));
    if (hash) {
      const hit = cards.find((x) => x.parts.some((p) => p.layerId === hash) || hash === `card-${x.key}`);
      if (hit) {
        v = 'topic';
        setOpenKeys(new Set([hit.key]));
        window.setTimeout(() => document.getElementById(hash)?.scrollIntoView(), 50);
      } else if (hash.startsWith('topic-')) v = 'topic';
    }
    if (c && !countries.some((x) => x.iso3 === c)) c = null;
    setView(v);
    setIso(c);
  }, [cards, countries]);

  const go = useCallback((v: View, c: string | null) => {
    setView(v);
    setIso(c);
    const sp = new URLSearchParams();
    if (v === 'country') sp.set('view', 'country');
    if (v === 'country' && c) sp.set('c', c);
    const qs = sp.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`);
  }, []);

  const toggle = (key: string) =>
    setOpenKeys((prev) => {
      const n = new Set(prev);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });

  const tab = (v: View, label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={view === v}
      className={`min-h-[44px] rounded-md border px-4 text-sm font-semibold ${view === v ? 'border-accent bg-accent text-white' : 'border-line bg-surface text-ink hover:border-accent'}`}
      onClick={() => go(v, v === 'country' ? iso : null)}
    >
      {label}
    </button>
  );

  const worldCards = cards.filter((c) => c.iso3 === WORLD && c.topic !== 'Boundaries');
  const shownCountries = countries.filter((c) => c.name.toLowerCase().includes(q.trim().toLowerCase()));
  const chosen = iso ? countries.find((c) => c.iso3 === iso) : undefined;
  const chosenCards = chosen ? cards.filter((c) => c.iso3 === chosen.iso3) : [];

  return (
    <div>
      <div role="tablist" aria-label="View" className="mt-4 flex gap-2">
        {tab('topic', 'By topic')}
        {tab('country', 'By country')}
      </div>

      {view === 'topic' && (
        <div role="tabpanel">
          <nav aria-label="Topics" className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span className="text-muted">On this page:</span>
            {topics.map((t) => <a key={t} href={`#${anchorOfTopic(t)}`}>{t}</a>)}
          </nav>
          {topics.map((t) => {
            const list = cards.filter((c) => c.topic === t);
            return (
              <section key={t} id={anchorOfTopic(t)} className="mt-8 scroll-mt-20">
                <h2 className="text-lg font-semibold">{t}</h2>
                <ZenodoLinks cards={list} />
                {list.map((c) => <Card key={c.key} card={c} open={openKeys.has(c.key)} onToggle={() => toggle(c.key)} worldNote={false} />)}
              </section>
            );
          })}
        </div>
      )}

      {view === 'country' && (
        <div role="tabpanel" className="mt-4">
          {!chosen && (
            <>
              <label className="sr-only" htmlFor="data-country-q">Find a country</label>
              <input id="data-country-q" type="search" autoComplete="off" placeholder="Find a country" className="h-11 w-full rounded-md border border-line bg-surface px-3 text-sm" value={q} onChange={(e) => setQ(e.target.value)} />
              <ul className="mt-3 divide-y divide-line rounded-lg border border-line bg-surface">
                {shownCountries.map((c) => (
                  <li key={c.iso3}>
                    <button type="button" className="flex min-h-[44px] w-full items-center justify-between px-3 text-left text-sm hover:bg-[#eef3f3]" onClick={() => go('country', c.iso3)}>
                      <span className="font-semibold">{c.name}</span>
                      <span className="text-muted">{c.n} {c.n === 1 ? 'indicator' : 'indicators'}</span>
                    </button>
                  </li>
                ))}
                {shownCountries.length === 0 && <li className="px-3 py-3 text-sm text-muted">No country with its own layers has this name.</li>}
              </ul>
              {worldCards.length > 0 && (
                <section className="mt-8">
                  <h2 className="text-lg font-semibold">World datasets</h2>
                  <p className="text-sm text-ink2">These layers cover many countries. Their files are whole, not cut by country.</p>
                  <ZenodoLinks cards={worldCards} />
                  {worldCards.map((c) => <Card key={c.key} card={c} open={openKeys.has(c.key)} onToggle={() => toggle(c.key)} worldNote={false} />)}
                </section>
              )}
            </>
          )}
          {chosen && (
            <section>
              <button type="button" className="text-sm text-accent hover:underline" onClick={() => go('country', null)}>← All countries</button>
              <h2 className="mt-2 text-lg font-semibold">{chosen.name}</h2>
              <ZenodoLinks cards={chosenCards} />
              {chosenCards.map((c) => <Card key={c.key} card={c} open={openKeys.has(c.key)} onToggle={() => toggle(c.key)} worldNote={false} />)}
              {worldCards.length > 0 && (
                <>
                  <h2 className="mt-8 text-lg font-semibold">World datasets</h2>
                  <p className="text-sm text-ink2">They cover {chosen.name} and other countries. Their files are whole, not cut by country.</p>
                  <ZenodoLinks cards={worldCards} />
                  {worldCards.map((c) => <Card key={c.key} card={c} open={openKeys.has(c.key)} onToggle={() => toggle(c.key)} worldNote />)}
                </>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
