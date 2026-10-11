'use client';

import Link from 'next/link';
import { X } from 'lucide-react';
import CopyButton from '@/components/CopyButton';
import type { FieldDef, LayerEntry, Meta } from '@/lib/data';
import { checkedByLine, formatBytes, formatNumber, isoDate, recordCitation } from '@/lib/format';
import { VOLTAGE_BANDS } from '@/lib/style';
import type { CardState, MapData } from './types';

const HIDDEN_FIELDS = new Set(['unit_id', 'fips', 'name', 'coverage_status']);
const FORMATS: { key: string; label: string }[] = [
  { key: 'csv', label: 'CSV' },
  { key: 'parquet', label: 'GeoParquet' },
  { key: 'geojson.gz', label: 'GeoJSON' },
];

function humanize(name: string): string {
  const s = name.replace(/_(mw|kv|km)$/, '').replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function nullText(f: FieldDef | undefined, covered: boolean): string {
  const nm = f?.null_meaning;
  if (nm && typeof nm === 'object') {
    const t = covered ? nm.covered : nm.not_covered;
    if (t) return t;
  } else if (typeof nm === 'string' && nm) return nm;
  return covered ? 'No value recorded for this unit.' : 'Not covered by this layer.';
}

function sourceLine(meta: Meta): string {
  const p = meta.sources.find((s) => s.role === 'primary') ?? meta.sources[0];
  const through = meta.freshness.source_current_through;
  return `Source: ${p.product} · ${p.edition}${through ? ` · data through ${through}` : ''} · built ${isoDate(meta.freshness.built_at)}`;
}

function Downloads({ layer }: { layer: LayerEntry }) {
  return (
    <div className="mt-3">
      <p className="text-xs text-muted">Download layer</p>
      <div className="mt-1 flex flex-wrap gap-2">
        {FORMATS.filter((f) => layer.files[f.key]).map((f) => (
          <a key={f.key} className="btn" href={layer.files[f.key].url} rel="noopener">
            {f.label} <span className="font-normal text-muted">{formatBytes(layer.files[f.key].bytes)}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function Shell({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <aside
      className="absolute inset-x-0 bottom-0 z-20 flex max-h-[68%] flex-col rounded-t-xl border border-line bg-surface shadow-lg md:inset-x-auto md:bottom-auto md:right-3 md:top-3 md:max-h-[calc(100%-1.5rem)] md:w-[24rem] md:rounded-xl"
      aria-label="Details"
    >
      <div className="flex items-start justify-between gap-2 px-4 pt-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold leading-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 break-all text-xs text-muted">{subtitle}</p>}
        </div>
        <button type="button" className="-mr-2 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center" aria-label="Close" onClick={onClose}>
          <X size={20} aria-hidden />
        </button>
      </div>
      <div className="overflow-y-auto px-4 pb-4 text-sm">{children}</div>
    </aside>
  );
}

function ValueRows({ layer, meta, props }: { layer: LayerEntry; meta: Meta; props: Record<string, unknown> }) {
  const covered = props.coverage_status === 'covered';
  const valueField = meta.display?.value_field;
  const fields = meta.fields.filter((f) => !HIDDEN_FIELDS.has(f.name) && layer.tiles.fields.includes(f.name));
  const firstNull = fields.find((f) => f.null_meaning);

  if (!covered) {
    const note = typeof props.coverage_note === 'string' && props.coverage_note ? props.coverage_note : nullText(firstNull, false);
    return (
      <div className="mt-3 rounded-md border border-dashed border-[#8a8f96] p-3">
        <p className="font-semibold">Not covered</p>
        <p className="mt-1 text-ink2">{note}</p>
        <p className="mt-1 text-xs text-muted">Empty means not covered, not zero.</p>
      </div>
    );
  }
  return (
    <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-2">
      {fields.map((f) => {
        const v = props[f.name];
        let text: string;
        let note = '';
        if (v === null || v === undefined || v === '') text = nullText(f, true);
        else if (typeof v === 'boolean') text = v ? 'Yes' : 'No';
        else if (typeof v === 'number') {
          text = `${formatNumber(v, 1)}${f.unit ? ` ${f.unit}` : ''}`;
          if (v === 0 && f.name === valueField && meta.display?.zero_class) note = 'none listed in the source';
        } else text = String(v);
        return (
          <div key={f.name} className="contents">
            <dt className="text-ink2" title={f.description}>{humanize(f.name)}</dt>
            <dd className="text-right font-medium">
              {text}
              {note && <span className="block text-xs font-normal text-muted">{note}</span>}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export default function InfoCard({ data, card, onClose }: { data: MapData; card: CardState; onClose: () => void }) {
  if (!card) return null;
  const layer = data.layers.find((l) => l.layer_id === card.layerId);
  if (!layer) return null;
  const meta = data.metas[layer.meta_id];
  const anchor = data.anchors[layer.layer_id];

  if (card.type === 'layer') {
    const doi = data.datasets[layer.dataset].doi;
    return (
      <Shell title={layer.title} subtitle={`${layer.level} · ${meta.release.dataset} v${meta.release.version}`} onClose={onClose}>
        <p className="mt-2">{meta.description}</p>
        <p className="mt-3"><strong>Coverage.</strong> {meta.coverage.geography}</p>
        {meta.coverage.known_gaps.length > 0 && (
          <>
            <p className="mt-3 font-semibold">Known gaps</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-ink2">
              {meta.coverage.known_gaps.map((g) => <li key={g}>{g}</li>)}
            </ul>
          </>
        )}
        <p className="mt-3"><strong>Freshness.</strong> Data through {meta.freshness.source_current_through ?? 'n/a'} · built {isoDate(meta.freshness.built_at)} · updates: {meta.freshness.source_cadence}</p>
        <p className="mt-3"><strong>Licence.</strong> <a href={meta.license.url}>{meta.license.name}</a></p>
        <blockquote className="mt-1 border-l-4 border-line pl-3 text-xs text-ink2">{meta.license.attribution_text}</blockquote>
        <p className="mt-3">{checkedByLine(meta)}</p>
        <Downloads layer={layer} />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <CopyButton text={meta.citation.text} label="Cite this layer" />
          {anchor && <Link href={`/methodology/#${anchor}`}>Methodology →</Link>}
        </div>
        {doi && <p className="mt-3 text-xs text-muted">DOI <a href={`https://doi.org/${doi}`}>{doi}</a></p>}
      </Shell>
    );
  }

  const p = card.props;
  const isLine = layer.tiles.geometry_type === 'line';
  const key = String(isLine ? p.record_id ?? '' : p.unit_id ?? '');

  if (isLine) {
    const kv = typeof p.voltage_kv === 'number' && p.voltage_kv > 0 ? `${formatNumber(p.voltage_kv, 0)} kV` : 'Not recorded';
    const band = VOLTAGE_BANDS.find((b) => b.id === p.voltage_band)?.label ?? String(p.voltage_band ?? '');
    const rows: [string, string][] = [
      ['Segment ID', key],
      ['Voltage', kv],
      ['Voltage class', String(p.voltage_class ?? '—')],
      ['Voltage band', band],
      ['Owner', String(p.owner ?? '—')],
      ['Status', String(p.status ?? '—')],
    ];
    return (
      <Shell title="Transmission line segment" subtitle={layer.title} onClose={onClose}>
        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-2">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-ink2">{k}</dt>
              <dd className="break-words text-right font-medium">{v}</dd>
            </div>
          ))}
        </dl>
        <Footer layer={layer} meta={meta} anchor={anchor} cite={recordCitation(meta, key)} />
      </Shell>
    );
  }

  return (
    <Shell title={String(p.name ?? key)} subtitle={`${key} · ${layer.title}`} onClose={onClose}>
      <ValueRows layer={layer} meta={meta} props={p} />
      <Footer layer={layer} meta={meta} anchor={anchor} cite={recordCitation(meta, key)} />
    </Shell>
  );
}

function Footer({ layer, meta, anchor, cite }: { layer: LayerEntry; meta: Meta; anchor?: string; cite: string }) {
  return (
    <>
      <p className="mt-4 text-xs text-ink2">{sourceLine(meta)}</p>
      <p className="mt-1 text-xs text-ink2">Licence: <a href={meta.license.url}>{meta.license.name}</a></p>
      <p className="mt-1 text-xs text-ink2">{checkedByLine(meta)}</p>
      <Downloads layer={layer} />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <CopyButton text={cite} label="Cite this record" />
        {anchor && <Link href={`/methodology/#${anchor}`}>Methodology →</Link>}
      </div>
    </>
  );
}
