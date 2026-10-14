'use client';

import Link from 'next/link';
import type { LayerEntry } from '@/lib/data';
import { capitalize, domainLabel, unitWord } from '@/lib/layers';
import { throughLabel } from '@/lib/format';
import { MODULE_BY_TYPE } from './modules';
import Shell from './Shell';
import type { MapData } from './types';

interface Props {
  data: MapData;
  iso3: string;
  name: string;
  /** the country's data layers in panel order; empty when the country has none yet */
  layers: LayerEntry[];
  activeId: string;
  overlays: Record<string, boolean>;
  onActive: (id: string) => void;
  onOverlay: (id: string, on: boolean) => void;
  onClose: () => void;
}

/**
 * Country card (ARCH 14.10, package 1c): opens when a country is chosen by a click on the globe.
 * Self-contained on purpose: it is the future country card of the panel v2.
 */
export default function CountryCard({ data, iso3, name, layers, activeId, overlays, onActive, onOverlay, onClose }: Props) {
  if (layers.length === 0) {
    return (
      <Shell title={name} subtitle={iso3} onClose={onClose}>
        <p className="mt-3 text-ink2">No layers for this country yet.</p>
      </Shell>
    );
  }

  const datasetNames = Array.from(new Set(layers.map((l) => l.dataset)));
  const domains = Array.from(new Set(layers.map((l) => l.domain)));

  const row = (l: LayerEntry) => {
    const exclusive = MODULE_BY_TYPE[l.tiles.geometry_type].exclusive;
    return (
      <li key={l.layer_id}>
        <label className="flex min-h-[44px] cursor-pointer items-center gap-2 py-1">
          {exclusive ? (
            <input type="radio" name="country-layer" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={activeId === l.layer_id} onChange={() => onActive(l.layer_id)} />
          ) : (
            <input type="checkbox" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={Boolean(overlays[l.layer_id])} onChange={(e) => onOverlay(l.layer_id, e.target.checked)} />
          )}
          <span className="leading-tight">
            <span className="block text-sm text-ink">{l.title}</span>
            <span className="block text-xs text-muted">{capitalize(unitWord(l))} · {throughLabel(data.metas[l.meta_id])}</span>
          </span>
        </label>
      </li>
    );
  };

  return (
    <Shell title={name} subtitle={iso3} onClose={onClose}>
      <ul className="mt-2 space-y-1 text-xs text-ink2">
        {datasetNames.map((n) => {
          const ds = data.datasets[n];
          return (
            <li key={n}>
              <span className="font-semibold text-ink">{n}</span>
              {ds && <> · version {ds.version}</>}
              {ds?.doi && <> · DOI <a href={`https://doi.org/${ds.doi}`}>{ds.doi}</a></>}
            </li>
          );
        })}
      </ul>

      <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Layers</p>
      {domains.map((d) => (
        <div key={d} className="mt-1">
          {domains.length > 1 && <p className="text-xs text-ink2">{domainLabel(d)}</p>}
          <ul>
            {[...layers.filter((l) => l.domain === d && MODULE_BY_TYPE[l.tiles.geometry_type].exclusive), ...layers.filter((l) => l.domain === d && !MODULE_BY_TYPE[l.tiles.geometry_type].exclusive)].map(row)}
          </ul>
        </div>
      ))}

      <p className="mt-3 text-sm"><Link href="/data/">All files</Link></p>
    </Shell>
  );
}
