'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { cutRecord, splitFields } from '@/lib/csv';
import { loadCsv } from '@/lib/csvLoad';
import type { LayerEntry, Meta } from '@/lib/data';
import {
  CAPACITY_UNKNOWN_CLASS, CAPACITY_UNKNOWN_NUMBER, CAPACITY_WITHHELD, classCapacity, epochTags, longDate, numberCapacity, parseLinks,
} from '@/lib/dcTexts';

type Props = { layer: LayerEntry; meta: Meta; props: Record<string, unknown>; anchor?: string };

export const str = (v: unknown): string => (typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '');

/** "In the Atlas" status of an Epoch site: the row of checks.csv (an extra file of the layer), fetched on click. */
function useCell(layer: LayerEntry, recordId: string): { status: string; ref: string } | 'loading' | 'error' | null {
  const file = layer.extra_files.find((f) => f.path === 'checks.csv');
  const [cell, setCell] = useState<{ status: string; ref: string } | 'loading' | 'error' | null>(file ? 'loading' : null);
  useEffect(() => {
    if (!file) return;
    let live = true;
    setCell('loading');
    loadCsv(file.url)
      .then((text) => {
        const cut = cutRecord(text, 'record_id', recordId);
        if (!live) return;
        if (!cut) return setCell({ status: 'not_checked', ref: '' });
        const head = splitFields(cut.header);
        const row = splitFields(cut.row);
        const at = (k: string) => (row[head.indexOf(k)] ?? '').trim();
        setCell({ status: at('status') || 'not_checked', ref: at('ref') });
      })
      .catch(() => live && setCell('error'));
    return () => {
      live = false;
    };
  }, [file, recordId]);
  return cell;
}

/** Capacity of a record: the value of the source, never our estimate ("10–99 MW · size class given by ...", or the unknown / withheld text). */
export function capacityOf(meta: Meta, p: Record<string, unknown>): string {
  const d = meta.display!;
  const sizeField = d.size_field!;
  const unit = meta.fields.find((f) => f.name === sizeField)?.unit ?? 'MW';
  const status = str(p.power_status);
  if (status === 'withheld') return CAPACITY_WITHHELD;
  if (d.size_classes?.length) {
    const cls = str(p[sizeField]);
    return cls && status !== 'not_found' ? classCapacity(cls, d.size_classes, d.size_breaks ?? [], unit) : CAPACITY_UNKNOWN_CLASS;
  }
  const v = p[sizeField];
  return typeof v === 'number' && status !== 'not_found' ? numberCapacity(v, unit, longDate(meta.freshness.source_current_through)) : CAPACITY_UNKNOWN_NUMBER;
}

/** The same in a few words for a line of a list: "10–99 MW", "unknown", "not published". */
export function capacityShort(meta: Meta, p: Record<string, unknown>): string {
  const s = capacityOf(meta, p).replace(/^Capacity: /, '');
  if (/^unknown/.test(s)) return 'unknown';
  if (/^not published/.test(s)) return 'not published';
  return s.split(' · ')[0];
}

/**
 * Point window of the world data-center layers (SPEC_DC_world 6): every row says whose statement it is.
 * Rows appear for the fields the tiles carry, so one component serves both sources.
 */
export default function DcPointRows({ layer, meta, props: p, anchor }: Props) {
  const fields = new Set(layer.tiles.fields);
  const has = (f: string) => fields.has(f);
  const source = layer.title.split('·')[1]?.trim() ?? 'the source';
  const cell = useCell(layer, str(p.record_id));
  const capacity = capacityOf(meta, p);

  const placeFrom = (() => {
    const s = str(p.coord_source);
    if (s === 'geonames_name') return 'from the record name';
    if (s === 'geonames_address' || s === 'census_place') return 'from the address';
    return '';
  })();
  const links = parseLinks(str(p.source_urls) || str(p.selected_sources));
  const disputed = str(p.control_iso3);

  const row = (label: string, value: React.ReactNode, from?: string) => (
    <div key={label} className="contents">
      <dt className="text-ink2">{label}</dt>
      <dd className="break-words text-right font-medium">
        {value}
        {from && <span className="block text-xs font-normal text-muted">{from}</span>}
      </dd>
    </div>
  );

  const operator = str(p.operator);
  const owner = str(p.owner);
  const users = str(p.users);
  const project = str(p.project);
  const statusRaw = str(p.status_raw);
  const year = str(p.start_year);

  return (
    <>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2">
        {has('operator') && operator && row('Operator', <>{operator}{str(p.operator_type) && ` (${str(p.operator_type)})`}</>, `Source: ${source}`)}
        {has('owner') && owner && row('Owner', epochTags(owner), `Source: ${source}`)}
        {has('users') && users && row('Users', epochTags(users), `Source: ${source}`)}
        {has('project') && project && row('Project', epochTags(project), `Source: ${source}`)}
        {has('status_raw') && statusRaw && row('Status', <>{statusRaw}{year && ` · since ${year}`}</>, `Source: ${source}`)}
        {row('Capacity', capacity.replace(/^Capacity: /, ''), `Source: ${source}`)}
        {has('place_name') && str(p.place_name) &&
          row(
            'Place',
            <>
              {str(p.place_name)}
              {placeFrom && ` — ${placeFrom}`}
            </>,
            'Place set by the project; the point marks the town, not the site',
          )}
        {cell && row('In the Atlas', cell === 'loading' ? 'Loading…' : cell === 'error' ? 'Could not read checks.csv' : cell.status === 'found' ? `found${cell.ref ? ` (${cell.ref.split(';').map((x) => x.trim()).join(', ')})` : ''}` : cell.status === 'not_found' ? 'not found' : 'not checked', 'Source: project check, checks.csv')}
      </dl>
      {placeFrom === 'from the record name' && anchor && (
        <p className="mt-1 text-xs text-ink2"><Link href={`/methodology/#${anchor}`}>How accurate is a place taken from the name? →</Link></p>
      )}
      {disputed && (
        <p className="mt-2 rounded-md border border-dashed border-[#8a8f96] p-2 text-xs text-ink2">
          In an area of disputed control (see <Link href="/methodology/">Boundaries</Link>). Control: {disputed}.
        </p>
      )}
      {links.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Sources given by {source}</p>
          <ul className="mt-1 space-y-1">
            {links.map((l) => (
              <li key={l.href} className="break-all">
                <a href={l.href} target="_blank" rel="noopener noreferrer">{l.label}</a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
