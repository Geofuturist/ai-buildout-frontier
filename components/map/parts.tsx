'use client';

import type { FieldDef, LayerEntry, Meta } from '@/lib/data';
import { formatBytes, formatNumber, isoDate } from '@/lib/format';
import { MODULE_BY_TYPE } from './modules';

const HIDDEN_FIELDS = new Set(['name', 'coverage_status']);
export const FORMATS: { key: string; label: string }[] = [
  { key: 'csv', label: 'CSV' },
  { key: 'parquet', label: 'GeoParquet' },
  { key: 'geojson.gz', label: 'GeoJSON' },
];

export function humanize(name: string): string {
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

export function sourceLine(meta: Meta): string {
  const p = meta.sources.find((s) => s.role === 'primary') ?? meta.sources[0];
  const through = meta.freshness.source_current_through;
  return `Source: ${p.product} · ${p.edition}${through ? ` · data through ${through}` : ''} · built ${isoDate(meta.freshness.built_at)}`;
}

export function Downloads({ layer }: { layer: LayerEntry }) {
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

export function ValueRows({ layer, meta, props, keyField }: { layer: LayerEntry; meta: Meta; props: Record<string, unknown>; keyField: string }) {
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

