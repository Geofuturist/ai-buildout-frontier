'use client';

import { useState } from 'react';
import { Download } from 'lucide-react';
import { buildRowsCsv, cutRows, safePart } from '@/lib/csv';
import { loadCsv } from '@/lib/csvLoad';
import type { LayerEntry, Meta } from '@/lib/data';
import { capitalize, unitWord } from '@/lib/layers';
import { levelWord } from '@/lib/indicators';
import type { CountryModel, Indicator } from '@/lib/indicators';
import { isWithin } from '@/lib/territory';
import type { Territory } from '@/lib/territory';
import DownloadMenu from './DownloadMenu';
import { Downloads } from './parts';
import RecordDownload, { sourceTexts } from './RecordDownload';
import type { MapData, UnitRef } from './types';

/** "Download ... inside this state: CSV" - rows of a published layer whose unit lies inside the chosen unit. */
export function InsideButton({ layer, meta, unit, territory, label }: { layer: LayerEntry; meta: Meta; unit: UnitRef; territory: Territory; label: string }) {
  const [state, setState] = useState<'idle' | 'busy' | 'error'>('idle');
  const csv = layer.files.csv;
  if (!csv) return null;
  const run = async () => {
    setState('busy');
    try {
      const text = await loadCsv(csv.url);
      const cut = cutRows(text, 'unit_id', (k) => k !== '' && isWithin(territory, k, unit.unit_id));
      if (!cut || cut.rows.length === 0) throw new Error('no rows');
      const cite = `${meta.citation.text} Rows: units of ${unit.name} (${cut.rows.length}).`;
      const out = buildRowsCsv(cut, cite, sourceTexts(meta));
      const href = URL.createObjectURL(new Blob([out], { type: 'text/csv;charset=utf-8' }));
      const a = document.createElement('a');
      a.href = href;
      a.download = `${safePart(layer.layer_id)}_${safePart(unit.unit_id)}_v${safePart(meta.release.version)}.csv`;
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
    <div className="mt-2">
      <button type="button" className="btn" onClick={run} disabled={state === 'busy'}>
        <Download size={16} aria-hidden className="mr-1.5" />
        {state === 'busy' ? 'Preparing…' : label}
      </button>
      {state === 'error' && <p role="alert" className="mt-1 text-xs text-[#9a2a00]">Nothing to download for this unit in this layer, or the file could not be read.</p>}
    </div>
  );
}

interface Props {
  data: MapData;
  /** the country's own layers, or null when it has none */
  model: CountryModel | null;
  iso3: string;
  indicator: Indicator | null;
  unit: UnitRef;
  territory: Territory | null;
}

/** Download block by scope: country - region - unit (SPEC_WEB_territory 5). Cuts are CSV only. */
export default function TerritoryDownloads({ data, model, iso3, indicator, unit, territory }: Props) {
  const word = levelWord(unit.level, indicator ?? undefined, iso3, data.unit_words).toLowerCase();

  if (unit.level === 0) {
    // Whole country: the full files of every level of the indicator, and of the points and lines
    return (
      <DownloadMenu label={`Download for ${unit.name}`}>
        {indicator?.levels.map(({ level, layer }) => (
          <div key={layer.layer_id} className="mt-2">
            <p className="text-xs text-ink2">{levelWord(level, indicator, iso3, data.unit_words)} level · {layer.title}</p>
            <Downloads layer={layer} />
          </div>
        ))}
        {(model?.overlays ?? []).map((layer) => (
          <div key={layer.layer_id} className="mt-2">
            <p className="text-xs text-ink2">{layer.title}</p>
            <Downloads layer={layer} />
          </div>
        ))}
      </DownloadMenu>
    );
  }

  const own = indicator?.levels.find((x) => x.level === unit.level);
  const finer = indicator?.levels.filter((x) => x.level > unit.level) ?? [];
  const points = (model?.overlays ?? []).filter((l) => l.tiles.geometry_type === 'point' && l.files.csv);

  return (
    <DownloadMenu label={`Download for ${unit.name}`}>
      {own && <RecordDownload layer={own.layer} meta={data.metas[own.layer.meta_id]} keyField="unit_id" keyValue={unit.unit_id} />}
      {territory ? (
        <>
          {finer.map(({ layer }) => (
            <InsideButton
              key={layer.layer_id}
              layer={layer}
              meta={data.metas[layer.meta_id]}
              unit={unit}
              territory={territory}
              label={`Download ${unitWord(layer)} data inside this ${word}: CSV`}
            />
          ))}
          {points.map((layer) => (
            <InsideButton
              key={layer.layer_id}
              layer={layer}
              meta={data.metas[layer.meta_id]}
              unit={unit}
              territory={territory}
              label={`Download ${unitWord(layer)} inside this ${word}: CSV`}
            />
          ))}
        </>
      ) : (
        <p className="mt-2 text-xs text-muted">Loading the list of units…</p>
      )}
      {!own && finer.length === 0 && points.length === 0 && <p className="mt-2 text-xs text-muted">{capitalize(word)} files are published for the whole country only.</p>}
    </DownloadMenu>
  );
}
