'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';
import CopyButton from '@/components/CopyButton';
import type { LayerEntry } from '@/lib/data';
import { checkedByLine, recordCitation, throughLabel } from '@/lib/format';
import { fillLevelOf, levelWord } from '@/lib/indicators';
import type { CountryModel, Indicator } from '@/lib/indicators';
import { capitalize, unitWord } from '@/lib/layers';
import { chainOf, unitName } from '@/lib/territory';
import type { Territory } from '@/lib/territory';
import TerritoryDownloads from './TerritoryDownloads';
import UnitValues from './UnitValues';
import type { MapData, UnitRef } from './types';

interface Props {
  data: MapData;
  countries: CountryModel[];
  /** the chosen country: its ISO3 code (even when it has no layers) */
  countryIso: string | null;
  countryName: string;
  model: CountryModel | null;
  indicator: Indicator | null;
  overlays: Record<string, boolean>;
  failed: Set<string>;
  /** the chosen unit; level 0 = the country */
  unit: UnitRef | null;
  territory: Territory | null;
  /** a record or layer card is shown instead of the panel */
  hidden: boolean;
  /** changes whenever the choice changes: opens the phone sheet */
  nonce: number;
  /** the level a click selects now (0, 1, 2) */
  selLevel: number;
  onIndicator: (key: string) => void;
  onOverlay: (id: string, on: boolean) => void;
  onCountry: (iso3: string) => void;
  onWorld: () => void;
  onCrumb: (unitId: string) => void;
  onInfo: (layerId: string) => void;
}

export default function TerritoryPanel(p: Props) {
  const { data, model, indicator, unit } = p;
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (p.nonce > 0) setOpen(true);
  }, [p.nonce]);

  const exclusiveRow = (ind: Indicator) => {
    const shown = fillLevelOf(ind, p.selLevel).layer;
    const meta = data.metas[shown.meta_id];
    const words = ind.levels.map((x) => unitWord(x.layer)).join(', ');
    return (
      <li key={ind.key} className="flex items-stretch">
        <label className="flex min-h-[44px] flex-1 cursor-pointer items-center gap-2 py-1">
          <input type="radio" name="indicator" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={indicator?.key === ind.key} onChange={() => p.onIndicator(ind.key)} />
          <span className="leading-tight">
            <span className="block text-sm text-ink">{ind.title}</span>
            <span className="block text-xs text-muted">{capitalize(words)} · {throughLabel(meta)}</span>
          </span>
        </label>
        <button type="button" className="flex h-11 w-11 shrink-0 items-center justify-center text-accent" aria-label={`About: ${shown.title}`} onClick={() => p.onInfo(shown.layer_id)}>
          <Info size={18} aria-hidden />
        </button>
      </li>
    );
  };

  const overlayRow = (l: LayerEntry) => (
    <li key={l.layer_id} className="flex items-stretch">
      <label className="flex min-h-[44px] flex-1 cursor-pointer items-center gap-2 py-1">
        <input type="checkbox" className="h-4 w-4 shrink-0 accent-[#0f6e6e]" checked={Boolean(p.overlays[l.layer_id])} onChange={(e) => p.onOverlay(l.layer_id, e.target.checked)} />
        <span className="leading-tight">
          <span className="block text-sm text-ink">{l.title}</span>
          <span className="block text-xs text-muted">
            {capitalize(unitWord(l))} · {throughLabel(data.metas[l.meta_id])}
            {p.failed.has(l.layer_id) && <strong className="ml-1 text-[#9a2a00]">· Failed to load</strong>}
          </span>
        </span>
      </label>
      <button type="button" className="flex h-11 w-11 shrink-0 items-center justify-center text-accent" aria-label={`About: ${l.title}`} onClick={() => p.onInfo(l.layer_id)}>
        <Info size={18} aria-hidden />
      </button>
    </li>
  );

  // Value of the active indicator at the level of the chosen unit
  const valueLayer = indicator && unit ? indicator.levels.find((x) => x.level === unit.level)?.layer : undefined;
  const chain = unit && p.countryIso ? chainOf(p.territory, unit.unit_id) : [];
  const word = unit ? levelWord(unit.level, indicator ?? undefined, p.countryIso ?? '', data.unit_words) : '';
  const citeLayer = valueLayer ?? (indicator ? fillLevelOf(indicator, p.selLevel).layer : undefined);
  const citeMeta = citeLayer ? data.metas[citeLayer.meta_id] : null;
  const anchor = citeLayer ? data.anchors[citeLayer.layer_id] : undefined;

  const title = p.countryIso ? (unit && unit.level > 0 ? unit.name : p.countryName) : 'Choose a country on the map';

  return (
    <aside
      className={`absolute inset-x-0 bottom-0 z-20 flex max-h-[58%] flex-col rounded-t-xl border border-line bg-surface shadow-lg md:inset-x-auto md:bottom-auto md:right-3 md:top-14 md:max-h-[calc(100%-12rem)] md:w-[24rem] md:rounded-xl ${p.hidden ? 'hidden' : ''}`}
      aria-label="Territory"
    >
      <button type="button" className="flex min-h-[48px] items-center justify-between px-4 text-left md:hidden" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="text-sm">
          <span className="font-semibold">{p.countryIso ? title : 'Territory'}</span>
          {!p.countryIso && <span className="text-ink2"> · choose a country</span>}
        </span>
        {open ? <ChevronDown size={20} aria-hidden /> : <ChevronUp size={20} aria-hidden />}
      </button>

      <div className={`${open ? 'block' : 'hidden'} overflow-y-auto px-4 pb-4 pt-1 text-sm md:block md:pt-3`}>
        {!p.countryIso && (
          <>
            <h2 className="text-base font-semibold leading-tight">Choose a country on the map</h2>
            <p className="mt-1 text-ink2">Countries with data:</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {p.countries.map((c) => (
                <button key={c.iso3} type="button" className="btn" onClick={() => p.onCountry(c.iso3)}>{c.name}</button>
              ))}
              <button type="button" className="btn" onClick={p.onWorld}>World</button>
            </div>
          </>
        )}

        {p.countryIso && (
          <>
            {/* Path up: country › region › unit */}
            <nav aria-label="Path" className="flex flex-wrap items-center gap-x-1 text-xs text-ink2">
              <button type="button" className="text-accent hover:underline" onClick={p.onWorld}>World</button>
              {(chain.length ? chain : [p.countryIso]).map((id, i, arr) => (
                <span key={id} className="flex items-center gap-1">
                  <span aria-hidden>›</span>
                  {i === arr.length - 1 && unit && unit.level === i ? (
                    <span className="font-semibold text-ink">{i === 0 ? p.countryName : unitName(p.territory, id)}</span>
                  ) : (
                    <button type="button" className="text-accent hover:underline" onClick={() => p.onCrumb(id)}>{i === 0 ? p.countryName : unitName(p.territory, id)}</button>
                  )}
                </span>
              ))}
            </nav>
            <h2 className="mt-2 text-base font-semibold leading-tight">{title}</h2>
            {unit && <p className="text-xs text-muted">{word} · {unit.unit_id}</p>}

            {!model && <p className="mt-3 text-ink2">No layers for this country yet.</p>}

            {model && (
              <>
                <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Indicators</p>
                <ul>{model.indicators.map(exclusiveRow)}</ul>
                {model.overlays.length > 0 && (
                  <>
                    <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-muted">On top of the map</p>
                    <ul>{model.overlays.map(overlayRow)}</ul>
                  </>
                )}

                {indicator && unit && (
                  <div className="mt-3 border-t border-line pt-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">{indicator.title}</p>
                    {valueLayer ? (
                      <UnitValues layer={valueLayer} meta={data.metas[valueLayer.meta_id]} unitId={unit.unit_id} />
                    ) : (
                      <p className="mt-2 rounded-md border border-dashed border-[#8a8f96] p-3 text-ink2">Not published at this level in this release.</p>
                    )}
                    {valueLayer && <p className="mt-2 text-xs text-ink2">{checkedByLine(data.metas[valueLayer.meta_id])}</p>}
                  </div>
                )}

                {unit && <TerritoryDownloads data={data} model={model} indicator={indicator} unit={unit} territory={p.territory} />}

                {citeLayer && citeMeta && unit && (
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <CopyButton
                      text={valueLayer && unit.level > 0 ? recordCitation(citeMeta, unit.unit_id) : citeMeta.citation.text}
                      label={valueLayer && unit.level > 0 ? 'Cite this record' : 'Cite this layer'}
                    />
                    {anchor && <Link href={`/methodology/#${anchor}`}>Methodology →</Link>}
                  </div>
                )}
                {citeLayer && <p className="mt-3 text-sm"><Link href="/data/">All files</Link></p>}
              </>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
