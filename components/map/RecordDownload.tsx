'use client';

import { useState } from 'react';
import { Download } from 'lucide-react';
import { buildRecordCsv, cutRecord, safePart } from '@/lib/csv';
import type { LayerEntry, Meta } from '@/lib/data';
import { loadCsv } from '@/lib/csvLoad';
import { recordCitation } from '@/lib/format';

/** Attribution texts of all sources of the layer, without repeats (a licence condition of CC BY and Licence Ouverte). */
export function sourceTexts(meta: Meta): string[] {
  const texts = meta.sources.map((s) => s.license.attribution_text).filter(Boolean);
  if (texts.length === 0 && meta.license.attribution_text) texts.push(meta.license.attribution_text);
  return [...new Set(texts)];
}

interface Props {
  layer: LayerEntry;
  meta: Meta;
  keyField: string;
  keyValue: string;
}

export default function RecordDownload({ layer, meta, keyField, keyValue }: Props) {
  const [state, setState] = useState<'idle' | 'busy' | 'error'>('idle');
  const csv = layer.files.csv;
  if (!csv) return null;

  const run = async () => {
    setState('busy');
    try {
      const text = await loadCsv(csv.url);
      const cut = cutRecord(text, keyField, keyValue);
      if (!cut) throw new Error('row not found');
      const out = buildRecordCsv(cut, recordCitation(meta, keyValue), sourceTexts(meta));
      const blob = new Blob([out], { type: 'text/csv;charset=utf-8' });
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = `${safePart(layer.layer_id)}_${safePart(keyValue)}_v${safePart(meta.release.version)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(href), 1000);
      setState('idle');
    } catch {
      setState('error');
    }
  };

  return (
    <div className="mt-3">
      <button type="button" className="btn" onClick={run} disabled={state === 'busy'}>
        <Download size={16} aria-hidden className="mr-1.5" />
        {state === 'busy' ? 'Preparing…' : 'Download this record: CSV'}
      </button>
      {state === 'error' && (
        <p role="alert" className="mt-1 text-xs text-[#9a2a00]">
          Could not prepare the file. The full layer files are on the Data page.
        </p>
      )}
    </div>
  );
}
