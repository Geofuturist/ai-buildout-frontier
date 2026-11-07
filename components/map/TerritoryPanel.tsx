'use client';

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronRight, ChevronLeft, ChevronUp } from 'lucide-react';
import CopyButton from '@/components/CopyButton';
import { checkedByLine, recordCitation } from '@/lib/format';
import { levelWord, shownLevelOf } from '@/lib/indicators';
import { WORLD } from '@/lib/layers';
import type { CountryModel, Indicator } from '@/lib/indicators';
import { chainOf, unitName } from '@/lib/territory';
import type { Territory } from '@/lib/territory';
import type { PanelRow } from '@/lib/panel';
import LayersPanel from './LayersPanel';
import TerritoryDownloads, { InsideButton } from './TerritoryDownloads';
import UnitValues from './UnitValues';
import UnitIndex from './UnitIndex';
import type { MapData, UnitRef } from './types';

interface Props {
  data: MapData;
  /** the chosen country: its ISO3 code (even when it has no layers) */
  countryIso: string | null;
  countryName: string;
  model: CountryModel | null;
  /** indicators that are not on the map (display.map = false): the card still shows their values */
  hiddenIndicators: Indicator[];
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
  /** layers of the chosen country: the dataset is chosen here, not in the panel on the left */
  countryRows: PanelRow[];
  overlays: Record<string, boolean>;
  failed: Set<string>;
  onColors: (row: PanelRow) => void;
  onPoints: (row: PanelRow, on: boolean) => void;
  legendOf: (row: PanelRow) => ReactNode;
  onInfo: (layerId: string) => void;
  onWorld: () => void;
  onCrumb: (unitId: string) => void;
}

export default function TerritoryPanel(p: Props) {
  const { data, model, indicator, unit } = p;
  const [open, setOpen] = useState(false);
  // Desktop: the card can be folded to the right edge; the choice is remembered
  const [folded, setFolded] = useState(false);
  useEffect(() => {
    try {
      if (window.localStorage.getItem('abf.territory.folded') === '1') setFolded(true);
    } catch {
      /* storage may be blocked */
    }
  }, []);
  const fold = (v: boolean) => {
    setFolded(v);
    try {
      window.localStorage.setItem('abf.territory.folded', v ? '1' : '0');
    } catch {
      /* ignore */
    }
  };
  useEffect(() => {
    if (p.nonce > 0) setOpen(true);
  }, [p.nonce]);

  const ownIndicator = indicator && indicator.iso3 !== WORLD ? indicator : null;
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

  // Is there anything of the country itself to show in this unit (a value block, or a file of a hidden indicator)
  const hasNational = !!unit && ((!!indicator && !coveredByIndex(data, indicator)) || p.hiddenIndicators.some((h) => !coveredByIndex(data, h) && h.levels.some((x) => x.level === unit.level)));
  return (
    <>
    {folded && !p.hidden && (
      <button type="button" className="absolute right-3 top-14 z-20 hidden h-9 items-center gap-1 rounded-md border border-line bg-surface pl-3 pr-2 text-[13px] font-semibold text-ink shadow-md hover:text-accent md:flex" aria-label="Show the territory card" aria-expanded={false} onClick={() => fold(false)}>
        {title}
        <ChevronLeft size={18} aria-hidden />
      </button>
    )}
    <aside
      className={`${folded ? 'md:hidden ' : ''}absolute inset-x-0 bottom-0 z-20 flex max-h-[58%] flex-col rounded-t-xl border border-line bg-surface shadow-lg md:inset-x-auto md:bottom-auto md:right-3 md:top-14 md:max-h-[calc(100%-12rem)] md:w-[24rem] md:rounded-xl ${p.hidden ? 'hidden' : ''}`}
      aria-label="Territory"
    >
      <button type="button" className="flex min-h-[48px] items-center justify-between px-4 text-left md:hidden" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="text-sm">
          <span className="font-semibold">{title}</span>
        </span>
        {open ? <ChevronDown size={20} aria-hidden /> : <ChevronUp size={20} aria-hidden />}
      </button>

      <button type="button" className="absolute right-2 top-2 hidden h-8 w-8 items-center justify-center rounded-md border border-line text-ink2 hover:text-accent md:flex" aria-label="Hide the territory card" aria-expanded onClick={() => fold(true)}>
        <ChevronRight size={18} aria-hidden />
      </button>
      <div className={`${open ? 'block' : 'hidden'} overflow-y-auto px-4 pb-4 pt-1 text-sm md:block md:pr-12 md:pt-3`}>
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

            {!model && !indicator && p.countryRows.length === 0 && p.hiddenIndicators.length === 0 && <p className="mt-3 text-ink2">No layers for this country yet.</p>}

            {p.countryRows.length > 0 && (
              <div className="mt-3 border-t border-line pt-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Layers of {p.countryName}</p>
                <LayersPanel rows={p.countryRows} activeFill={indicator?.key ?? null} overlays={p.overlays} failed={p.failed} onColors={p.onColors} onPoints={p.onPoints} onInfo={p.onInfo} legendOf={p.legendOf} openAll />
              </div>
            )}

            {unit && hasNational && (
              <NationalData data={data}>
                {indicator && unit && !coveredByIndex(data, indicator) && (
                  <div className="mt-3 border-t border-line pt-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">{indicator.title}</p>
                    {valueLayer ? (
                      <UnitValues layer={valueLayer} meta={data.metas[valueLayer.meta_id]} unitId={unit.unit_id} />
                    ) : (
                      <NoLevel data={data} indicator={indicator} unit={unit} territory={p.territory} iso3={p.countryIso} />
                    )}
                    {valueLayer && <p className="mt-2 text-xs text-ink2">{checkedByLine(data.metas[valueLayer.meta_id])}</p>}
                  </div>
                )}
                {/* Files of the country itself; files of the whole world are on the world card */}
                {unit && p.hiddenIndicators.filter((h) => !coveredByIndex(data, h)).map((h) => {
                  const l = h.levels.find((x) => x.level === unit.level)?.layer;
                  return l ? (
                    <div key={h.key} className="mt-3 border-t border-line pt-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{h.title}</p>
                      <UnitValues layer={l} meta={data.metas[l.meta_id]} unitId={unit.unit_id} />
                      <p className="mt-2 text-xs text-ink2">{checkedByLine(data.metas[l.meta_id])}</p>
                    </div>
                  ) : null;
                })}
              </NationalData>
            )}

            {unit && data.index && <UnitIndex index={data.index} iso3={p.countryIso} unit={unit} countryName={p.countryName} />}

            {unit && (model || ownIndicator) && <TerritoryDownloads data={data} model={model} iso3={p.countryIso} indicator={ownIndicator} unit={unit} territory={p.territory} />}

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
    </>
  );
}

/**
 * The data of the country itself (national layers) are folded into one colored plate when the territory index is on the
 * card, as the plates of the independent data are; without the index the blocks stay as they were.
 */
function NationalData({ data, children }: { data: MapData; children: ReactNode }) {
  const card = data.index?.card;
  if (!card) return <>{children}</>;
  return (
    <details className="group mt-3 overflow-hidden rounded-md border border-line">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-white [&::-webkit-details-marker]:hidden" style={{ backgroundColor: card.national_color ?? '#0f6e6e' }}>
        <span className="text-[13px] font-semibold leading-snug">{card.national_title ?? 'National data'}</span>
        <span aria-hidden className="text-xs transition-transform group-open:rotate-90">›</span>
      </summary>
      <div className="px-3 pb-3">{children}</div>
    </details>
  );
}

/**
 * The records of a layer that the territory index counts (content/site.json index_card.replaces) are shown once, from the
 * index: an older value block of the same records is left out of the card (its files stay on /data and in the downloads).
 */
function coveredByIndex(data: MapData, ind: Indicator): boolean {
  const ix = data.index;
  if (!ix || !ix.card.replaces) return false;
  const covered = new Set<string>();
  for (const [indexLayer, olds] of Object.entries(ix.card.replaces)) {
    if (ix.sets.some((s) => indexLayer in s.meta.layers)) for (const o of olds) covered.add(o);
  }
  return ind.levels.length > 0 && ind.levels.every((l) => covered.has(l.layer.layer_id));
}

/**
 * No data of the indicator at the level of the chosen unit (SPEC_WEB_territory r9 16 item 5): one line that says which
 * level there is and what can be downloaded inside the unit (rows cut by parent_id of units.csv).
 */
function NoLevel({ data, indicator, unit, territory, iso3 }: { data: MapData; indicator: Indicator; unit: UnitRef; territory: Territory | null; iso3: string }) {
  const word = levelWord(unit.level, indicator, iso3, data.unit_words).toLowerCase();
  const finer = indicator.levels.find((x) => x.level > unit.level);
  if (!finer) return <p className="mt-2 rounded-md border border-dashed border-[#8a8f96] p-3 text-ink2">No {word} data in this version.</p>;
  const finerWord = levelWord(finer.level, indicator, iso3, data.unit_words);
  return (
    <div className="mt-2 rounded-md border border-dashed border-[#8a8f96] p-3 text-ink2">
      <p>
        No {word} data in this version. {finerWord} data inside {unit.name}:
      </p>
      {territory ? (
        <InsideButton layer={finer.layer} meta={data.metas[finer.layer.meta_id]} unit={unit} territory={territory} label="CSV" />
      ) : (
        <p className="mt-1 text-xs text-muted">Loading the list of units…</p>
      )}
    </div>
  );
}
