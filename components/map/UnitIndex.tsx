'use client';

import { useEffect, useMemo, useState } from 'react';
import { buildRowsCsv, cutRows } from '@/lib/csv';
import type { IndexSource } from '@/lib/data';
import { approximateCount, basisOf, countryOnly, crossCounts, fillTemplate, fmtInt, fmtMw, levelColumn, noteCounts, parseRows, summarize } from '@/lib/indexCard';
import type { Joint, Row, Summary } from '@/lib/indexCard';
import type { UnitRef } from './types';

/** What a country file of a set holds: the whole text, read once and kept */
const cache = new Map<string, Promise<string | null>>();

function loadGz(url: string): Promise<string | null> {
  let p = cache.get(url);
  if (!p) {
    p = fetch(url).then(async (r) => {
      if (r.status === 404) return null;
      if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
      return new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).text();
    });
    p.catch(() => cache.delete(url));
    cache.set(url, p);
  }
  return p;
}

export interface SetData {
  id: string;
  header: string;
  rows: Row[];
  /** raw rows of the unit (for the download) */
  cut: { header: string; rows: string[]; eol: string };
  other: Row[];
}

const pretty = (v: string) => (v ? v.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : 'Not stated');
/** label of a value from the texts (site.json), else the value made readable */
const lab = (tx: Record<string, any>, v: string) => tx.value_labels?.[v] ?? pretty(v);

/**
 * The records of the chosen unit, counted by the published territory index (SPEC_INDEX_territory r5 §8). Counts are made
 * only from what the index declares additive; the card names the file and the basis of the assignment.
 */
export default function UnitIndex({ index, iso3, unit, countryName }: { index: IndexSource; iso3: string; unit: UnitRef; countryName: string }) {
  const [data, setData] = useState<SetData[] | 'loading' | 'failed'>('loading');
  const tx = index.card.texts;

  useEffect(() => {
    let live = true;
    setData('loading');
    const col = levelColumn(unit.level);
    Promise.all(
      index.sets.map(async (s) => {
        const text = s.meta.countries.includes(iso3) ? await loadGz(`${index.base}/${s.id}/${iso3}.csv.gz`) : null;
        const otherText = await loadGz(`${index.base}/${s.id}/adm0_other.csv.gz`);
        const cut = (text && cutRows(text, col, (k) => k === unit.unit_id)) || { header: '', rows: [], eol: '\n' };
        const oc = otherText ? cutRows(otherText, 'record_id', () => true) : null;
        return {
          id: s.id,
          header: cut.header,
          rows: cut.header ? parseRows(cut.header, cut.rows) : [],
          cut,
          other: oc ? parseRows(oc.header, oc.rows) : [],
        } as SetData;
      }),
    )
      .then((d) => live && setData(d))
      .catch(() => live && setData('failed'));
    return () => {
      live = false;
    };
  }, [index, iso3, unit.unit_id, unit.level]);

  if (data === 'loading') return <p className="mt-3 text-sm text-ink2">{tx.loading}</p>;
  if (data === 'failed') return <p role="alert" className="mt-3 text-sm text-[#9a2a00]">{tx.failed}</p>;

  return (
    <div className="mt-3 border-t border-line pt-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{index.card.title}</p>
      {index.sets.map((s) => {
        const d = data.find((x) => x.id === s.id);
        return d ? <SetBlock key={s.id} index={index} set={s} d={d} iso3={iso3} unit={unit} countryName={countryName} /> : null;
      })}
    </div>
  );
}

export function SetBlock({ index, set, d, iso3, unit, countryName }: { index: IndexSource; set: IndexSource['sets'][number]; d: SetData; iso3: string; unit: UnitRef; countryName: string }) {
  const c = index.card;
  const tx = c.texts;
  const summaries = useMemo(() => summarize(set.meta, d.rows), [set.meta, d.rows]);
  const lids = Object.keys(set.meta.layers);
  const cross = useMemo(() => crossCounts(d.other, iso3, unit.unit_id, unit.level), [d.other, iso3, unit]);
  const levels = set.meta.levels_by_country[iso3];

  return (
    <>
      {lids.map((lid) => {
        const rows = d.rows.filter((r) => r.layer_id === lid);
        const mine = summaries.filter((s) => s.layer_id === lid);
        return (
          <section key={lid} className="mt-3">
            <h3 className="text-sm font-semibold text-ink">{c.layer_titles[lid] ?? lid}</h3>
            {rows.length === 0 ? (
              <p className="mt-1 text-ink2">{tx.card_zero?.[lid] ?? ''}</p>
            ) : (
              <>
                {mine.map((s) => <SummaryView key={s.key} s={s} tx={tx} />)}
                <LayerNotes tx={tx} rows={rows} unit={unit} country={countryName} hasAdm1={levels?.adm1 ?? false} hasAdm2={levels?.adm2 ?? false} />
              </>
            )}
          </section>
        );
      })}
      {(cross.here > 0 || cross.away > 0) && (
        <div className="mt-2 space-y-1 text-xs text-ink2">
          {cross.here > 0 && <p>{fillTemplate(tx.card_other_country_here, { n: cross.here })}</p>}
          {cross.away > 0 && <p>{fillTemplate(tx.card_other_country_away, { n: cross.away, country: countryName })}</p>}
        </div>
      )}
      {d.rows.length > 0 && <RecordList index={index} set={set} d={d} unit={unit} />}
      <p className="mt-2 text-xs text-muted">{fillTemplate(tx.totals_note, { index_file: `${set.id}/${iso3}.csv.gz`, version: `abf-index ${set.version}` })}</p>
    </>
  );
}

function SummaryView({ s, tx }: { s: Summary; tx: Record<string, any> }) {
  const label = tx.aggregations_labels?.[s.key] ?? s.key;
  if (s.distinct) {
    return (
      <p className="mt-1 text-ink2">
        {label}: <b className="text-ink">{fmtInt(s.distinct.n)}</b>
      </p>
    );
  }
  if (s.joint) {
    // type × status: the count and the sum of the same cell; sums only inside one cell
    const byFirst = new Map<string, Joint['cells']>();
    for (const cell of s.joint.cells) {
      const k = cell.values[0];
      byFirst.set(k, [...(byFirst.get(k) ?? []), cell]);
    }
    return (
      <div className="mt-1">
        <p className="text-ink2">{label}</p>
        <ul className="mt-1 space-y-0.5 text-xs text-ink2">
          {[...byFirst].map(([k, cells]) => (
            <li key={k}>
              <span className="font-medium text-ink">{lab(tx, k)}</span>: {cells.map((x) => `${lab(tx, x.values[1] ?? '')} ${fmtInt(x.n)}${x.sum != null ? `, ${fmtMw(x.sum)}` : ''}`).join(' · ')}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <div className="mt-1">
      <p className="text-ink2">
        {label}: <b className="text-ink">{fmtInt(s.n)}</b>
      </p>
      {s.total && <p className="text-ink2">{s.total.label}: <b className="text-ink">{fmtMw(s.total.value)}</b></p>}
      {s.hists.map((h) => (
        <p key={h.field} className="mt-1 text-xs text-ink2">
          <span className="font-medium">{tx.field_labels?.[h.field] ?? h.field}:</span> {h.items.map((i) => `${lab(tx, i.value)} ${fmtInt(i.n)}`).join(' · ')}
        </p>
      ))}
    </div>
  );
}

function LayerNotes({ tx, rows, unit, country, hasAdm1, hasAdm2 }: { tx: Record<string, any>; rows: Row[]; unit: UnitRef; country: string; hasAdm1: boolean; hasAdm2: boolean }) {
  const basis = basisOf(rows, unit.level);
  const approx = approximateCount(rows);
  const notes = noteCounts(rows);
  const only = unit.level === 0 ? countryOnly(rows, hasAdm1) : 0;
  const lines: string[] = [];
  if (basis !== 'none') lines.push(fillTemplate(tx.card_basis, { basis: tx[`card_basis_${basis}`] }));
  if (approx > 0) lines.push(fillTemplate(tx.card_approximate, { n_approx: fmtInt(approx), n: fmtInt(rows.length) }));
  if (only > 0) lines.push(fillTemplate(tx.card_country_only, { n: fmtInt(only), country }));
  if (unit.level === 0 && !hasAdm1) lines.push(fillTemplate(tx.card_level_missing, { country, level_word: 'regional' }));
  if (unit.level === 1 && !hasAdm2) lines.push(fillTemplate(tx.card_level_missing, { country, level_word: 'second-level' }));
  return (
    <div className="mt-2 space-y-1 text-xs text-ink2">
      {lines.map((l) => <p key={l}>{l}</p>)}
      {notes.length > 0 && (
        <ul className="list-disc pl-4">
          {notes.map((n) => <li key={n.note}>{tx.card_unit_note?.[n.note] ?? n.note}: {fmtInt(n.n)}</li>)}
        </ul>
      )}
    </div>
  );
}

function RecordList({ index, set, d, unit }: { index: IndexSource; set: IndexSource['sets'][number]; d: SetData; unit: UnitRef }) {
  const c = index.card;
  const tx = c.texts;
  const shown = d.rows.slice(0, c.list_max);
  const titleOf = (r: Row) => c.title_fields.map((f) => r[f]).find(Boolean) ?? r.record_id;
  const detailOf = (r: Row) =>
    c.detail_fields
      .map((f) => (r[f] ? (f.endsWith('_mw') ? fmtMw(Number(r[f])) : lab(tx, r[f])) : ''))
      .filter(Boolean)
      .join(' · ');
  const download = () => {
    const cite = `Territory index ${set.id}, abf-index ${set.version}; unit ${unit.unit_id}; license ${set.license}`;
    const blob = new Blob([buildRowsCsv(d.cut, cite, [`${set.id}/abf-index ${set.version}`])], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${set.id}-index-${unit.unit_id}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-accent">{tx.list_title} ({fmtInt(d.rows.length)})</summary>
      <ul className="mt-1 max-h-60 space-y-1 overflow-y-auto text-xs">
        {shown.map((r) => (
          <li key={r.record_id}>
            <span className="text-ink">{titleOf(r)}</span> <span className="text-muted">{detailOf(r)}</span>
          </li>
        ))}
      </ul>
      {d.rows.length > shown.length && <p className="mt-1 text-xs text-muted">First {shown.length} of {fmtInt(d.rows.length)}. All rows are in the download.</p>}
      <button type="button" className="mt-2 rounded-md border border-line px-3 py-1 text-xs text-accent hover:bg-[#eef6f5]" onClick={download}>
        {tx.download}
      </button>
    </details>
  );
}
