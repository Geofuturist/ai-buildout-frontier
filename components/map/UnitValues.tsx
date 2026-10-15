'use client';

import { useEffect, useState } from 'react';
import { cutRecord, typedRow } from '@/lib/csv';
import { loadCsv } from '@/lib/csvLoad';
import type { LayerEntry, Meta } from '@/lib/data';
import { ValueRows } from './parts';

/** Values of one unit in the layer of its own level, read from the published CSV (no totals are ever computed). */
export default function UnitValues({ layer, meta, unitId }: { layer: LayerEntry; meta: Meta; unitId: string }) {
  const [state, setState] = useState<{ props: Record<string, unknown> | null; error: boolean } | 'loading'>('loading');
  const csvUrl = layer.files.csv?.url;

  useEffect(() => {
    let live = true;
    setState('loading');
    if (!csvUrl) {
      setState({ props: null, error: true });
      return;
    }
    loadCsv(csvUrl)
      .then((text) => {
        const cut = cutRecord(text, 'unit_id', unitId);
        const types = Object.fromEntries(meta.fields.map((f) => [f.name, f.type]));
        if (live) setState({ props: cut ? typedRow(cut.header, cut.row, types) : null, error: false });
      })
      .catch(() => live && setState({ props: null, error: true }));
    return () => {
      live = false;
    };
  }, [csvUrl, unitId, meta.fields]);

  if (state === 'loading') return <p className="mt-3 text-sm text-ink2">Loading values…</p>;
  if (state.error) return <p role="alert" className="mt-3 text-sm text-[#9a2a00]">Could not read the values. The layer files are on the Data page.</p>;
  if (!state.props) return <p className="mt-3 text-sm text-ink2">This unit has no row in the layer.</p>;
  return <ValueRows layer={layer} meta={meta} props={state.props} keyField="unit_id" />;
}
