'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp } from 'lucide-react';
import CopyButton from '@/components/CopyButton';
import { checkedByLine, recordCitation } from '@/lib/format';
import { levelWord, shownLevelOf } from '@/lib/indicators';
import type { CountryModel, Indicator } from '@/lib/indicators';
import { chainOf, unitName } from '@/lib/territory';
import type { Territory } from '@/lib/territory';
import TerritoryDownloads from './TerritoryDownloads';
import UnitValues from './UnitValues';
import type { MapData, UnitRef } from './types';

interface Props {
  data: MapData;
  /** the chosen country: its ISO3 code (even when it has no layers) */
  countryIso: string | null;
  countryName: string;
  model: CountryModel | null;
  /** the fill that is on, when it applies to the chosen country (its own or a world one) */
  indicator: Indicator | null;
  /** the chosen unit; level 0 = the country */
  unit: UnitRef | null;
  territory: Territory | null;
  /** a record or layer card is shown instead of the panel */
  hidden: boolean;
  /** changes whenever the choice changes: opens the phone sheet */
  nonce: number;
  /** the level a click selects now (0, 1, 2) */
  selLevel: number;
  onWorld: () => void;
  onCrumb: (unitId: string) => void;
}

export default function TerritoryPanel(p: Props) {
  const { data, model, indicator, unit } = p;
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (p.nonce > 0) setOpen(true);
  }, [p.nonce]);

  // Value of the active indicator at the level of the chosen unit
  const valueLayer = indicator && unit ? indicator.levels.find((x) => x.level === unit.level)?.layer : undefined;
  const chain = unit && p.countryIso ? chainOf(p.territory, unit.unit_id) : [];
  const word = unit ? levelWord(unit.level, indicator ?? undefined, p.countryIso ?? '', data.unit_words) : '';
  const citeLayer = valueLayer ?? (indicator ? shownLevelOf(indicator, p.selLevel).layer : undefined);
  const citeMeta = citeLayer ? data.metas[citeLayer.meta_id] : null;
  const anchor = citeLayer ? data.anchors[citeLayer.layer_id] : undefined;

  const title = unit && unit.level > 0 ? unit.name : p.countryName;

  // World view: no panel, the start globe marks the countries with data
  if (!p.countryIso) return null;

  return (
    <aside
      className={`absolute inset-x-0 bottom-0 z-20 flex max-h-[58%] flex-col rounded-t-xl border border-line bg-surface shadow-lg md:inset-x-auto md:bottom-auto md:right-3 md:top-14 md:max-h-[calc(100%-12rem)] md:w-[24rem] md:rounded-xl ${p.hidden ? 'hidden' : ''}`}
      aria-label="Territory"
    >
      <button type="button" className="flex min-h-[48px] items-center justify-between px-4 text-left md:hidden" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="text-sm">
          <span className="font-semibold">{title}</span>
        </span>
        {open ? <ChevronDown size={20} aria-hidden /> : <ChevronUp size={20} aria-hidden />}
      </button>

      <div className={`${open ? 'block' : 'hidden'} overflow-y-auto px-4 pb-4 pt-1 text-sm md:block md:pt-3`}>
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

            {!model && !indicator && <p className="mt-3 text-ink2">No layers for this country yet.</p>}

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

            {unit && (model || indicator) && <TerritoryDownloads data={data} model={model} iso3={p.countryIso} indicator={indicator} unit={unit} territory={p.territory} />}

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
      </div>
    </aside>
  );
}
