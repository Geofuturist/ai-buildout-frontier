'use client';

import Link from 'next/link';
import CopyButton from '@/components/CopyButton';
import type { FieldDef, LayerEntry, Meta } from '@/lib/data';
import { checkedByLine, formatBytes, formatNumber, isoDate, recordCitation } from '@/lib/format';
import { capitalize, recordNoun } from '@/lib/layers';
import { MODULE_BY_TYPE } from './modules';
import RecordDownload from './RecordDownload';
import Shell from './Shell';
import type { CardState, MapData } from './types';

const HIDDEN_FIELDS = new Set(['name', 'coverage_status']);
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

function ValueRows({ layer, meta, props, keyField }: { layer: LayerEntry; meta: Meta; props: Record<string, unknown>; keyField: string }) {
  const mod = MODULE_BY_TYPE[layer.tiles.geometry_type];
  const covered = props.coverage_status === undefined || props.coverage_status === 'covered';
  const valueField = meta.display?.value_field;
  const fields = meta.fields.filter((f) => !HIDDEN_FIELDS.has(f.name) && f.name !== keyField && layer.tiles.fields.includes(f.name));
  const firstNull = fields.find((f) => f.null_meaning);

  if (!covered) {
    // The record's own coverage_note if the tile has one, otherwise the layer's null_meaning.not_covered
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
        else {
          const custom = mod.formatValue?.(f, v, meta) ?? null;
          if (custom !== null) text = custom;
          else if (typeof v === 'boolean') text = v ? 'Yes' : 'No';
          else if (typeof v === 'number') {
            text = `${formatNumber(v, 1)}${f.unit ? ` ${f.unit}` : ''}`;
            if (v === 0 && f.name === valueField && meta.display?.zero_class) note = 'none listed in the source';
          } else text = String(v);
        }
        return (
          <div key={f.name} className="contents">
            <dt className="text-ink2" title={f.description}>{humanize(f.name)}</dt>
            <dd className="break-words text-right font-medium">
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
  if (!card || card.type === 'country') return null;
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
        <p className="mt-3"><strong>License.</strong> <a href={meta.license.url}>{meta.license.name}</a></p>
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

  const mod = MODULE_BY_TYPE[layer.tiles.geometry_type];
  const p = card.props;
  const key = String(p[mod.keyField] ?? '');
  const noun = recordNoun(layer);
  const title = typeof p.name === 'string' && p.name ? p.name : `${capitalize(noun)} ${key}`;

  return (
    <Shell title={title} subtitle={`${key} · ${layer.title}`} onClose={onClose}>
      <ValueRows layer={layer} meta={meta} props={p} keyField={mod.keyField} />
      <p className="mt-4 text-xs text-ink2">{sourceLine(meta)}</p>
      <p className="mt-1 text-xs text-ink2">License: <a href={meta.license.url}>{meta.license.name}</a></p>
      <p className="mt-1 text-xs text-ink2">{checkedByLine(meta)}</p>
      {mod.recordDownload && key && <RecordDownload layer={layer} meta={meta} keyField={mod.keyField} keyValue={key} />}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <CopyButton text={recordCitation(meta, key)} label={mod.recordDownload ? 'Cite this record' : `Cite this ${noun}`} />
        {anchor && <Link href={`/methodology/#${anchor}`}>Methodology →</Link>}
      </div>
      <p className="mt-3 text-sm"><Link href={`/data/#${layer.layer_id}`}>All files of this layer</Link></p>
    </Shell>
  );
}
