// Indicators and levels (SPEC_WEB_territory 2 and 4). Pure functions: no layer ids, country codes or field names.
import type { LayerEntry, Meta } from './data';
import { capitalize, unitWord } from './layers';

export type LevelId = 'ADM0' | 'ADM1' | 'ADM2';
export const LEVEL_IDS: LevelId[] = ['ADM0', 'ADM1', 'ADM2'];

export function levelNumber(level: string | undefined | null): number {
  const m = /(\d+)/.exec(level ?? '');
  return m ? Number(m[1]) : 99;
}

/** An indicator: the layers of one source and one country, one per level (SPEC_WEB_territory 2). */
export interface Indicator {
  key: string;
  iso3: string;
  /** group title: the layer title without its last " · " fragment */
  title: string;
  domain: string;
  /** coarse to fine */
  levels: { level: number; layer: LayerEntry }[];
}

/** Group key: display.series if the meta has it, otherwise the title without its last " · " fragment. */
export function indicatorTitle(layer: LayerEntry, meta: Meta | undefined): string {
  const series = (meta?.display as { series?: string } | undefined)?.series;
  if (series) return series;
  const parts = layer.title.split('·').map((p) => p.trim());
  return parts.length > 1 ? parts.slice(0, -1).join(' · ') : layer.title;
}

/** `fills` are the exclusive (polygon) layers of ONE country in panel order. */
export function groupIndicators(iso3: string, fills: LayerEntry[], metas: Record<string, Meta>): Indicator[] {
  const out: Indicator[] = [];
  for (const l of fills) {
    const title = indicatorTitle(l, metas[l.meta_id]);
    let g = out.find((x) => x.title === title);
    if (!g) {
      g = { key: `${iso3}|${title}`, iso3, title, domain: l.domain, levels: [] };
      out.push(g);
    }
    g.levels.push({ level: levelNumber(l.level), layer: l });
  }
  for (const g of out) g.levels.sort((a, b) => a.level - b.level);
  return out;
}

/** Selection level from the zoom (0 country, 1 ADM1, 2 ADM2). `available` = levels the country has in the boundaries. */
export function selectionLevel(zoom: number, levelZoom: { ADM1: number; ADM2: number }, available: Set<number> | null): number {
  let lvl = zoom >= levelZoom.ADM2 ? 2 : zoom >= levelZoom.ADM1 ? 1 : 0;
  while (lvl > 0 && available && !available.has(lvl)) lvl--;
  return lvl;
}

/**
 * Fill layer of an indicator: the finest of its layers not finer than the selection level; if there is none,
 * the coarsest it has.
 */
export function fillLevelOf(ind: Indicator, sel: number): { level: number; layer: LayerEntry } {
  const ok = ind.levels.filter((x) => x.level <= sel);
  return ok.length ? ok[ok.length - 1] : ind.levels[0];
}

/** Word for a level: the last title fragment of the indicator layer of that level, else the registry word, ADM0 = Country. */
export function levelWord(level: number, ind: Indicator | undefined, iso3: string, unitWords: Record<string, Record<string, string>>): string {
  if (level === 0) return 'Country';
  const own = ind?.levels.find((x) => x.level === level);
  if (own) return capitalize(unitWord(own.layer));
  const reg = unitWords[iso3]?.[`ADM${level}`];
  return reg ? capitalize(reg) : `Level ${level}`;
}

export interface CountryModel {
  iso3: string;
  name: string;
  indicators: Indicator[];
  /** points and lines of the country: separate flags on top of the fill */
  overlays: LayerEntry[];
}

/** Countries with layers, in panel order (the country of the default layer first), each with its indicators. */
export function buildCountries(
  groups: { iso3: string; name: string; domains: { domain: string; layers: LayerEntry[] }[] }[],
  metas: Record<string, Meta>,
  isFill: (l: LayerEntry) => boolean,
): CountryModel[] {
  return groups.map((g) => {
    const layers = g.domains.flatMap((d) => d.layers);
    return {
      iso3: g.iso3,
      name: g.name,
      indicators: groupIndicators(g.iso3, layers.filter(isFill), metas),
      overlays: layers.filter((l) => !isFill(l)),
    };
  });
}
