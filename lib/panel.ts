// Rows of the layers panel (SPEC_WEB_territory r4 12-13). Pure functions: no layer ids, no country codes.
import type { LayerEntry, Meta } from './data';
import { throughLabel } from './format';
import { indicatorTitle } from './indicators';
import type { CountryModel, Indicator } from './indicators';
import { WORLD, capitalize, unitWord } from './layers';

export const TOPICS = ['Data centers', 'Energy', 'Environment', 'Policy', 'Other'] as const;
export type Topic = (typeof TOPICS)[number];

const TOPIC_BY_DOMAIN: Record<string, Topic> = { dc: 'Data centers', energy: 'Energy', restrictions: 'Policy' };

/** display.topic if the meta has it and it is a known topic, otherwise by the domain; anything else is "Other". */
export function topicFor(layer: LayerEntry, meta: Meta | undefined): Topic {
  const t = meta?.display?.topic;
  if (t) {
    const hit = TOPICS.find((x) => x.toLowerCase() === t.toLowerCase());
    if (hit) return hit;
  }
  return TOPIC_BY_DOMAIN[layer.domain] ?? 'Other';
}

export interface PanelRow {
  key: string;
  kind: 'fill' | 'overlay';
  topic: Topic;
  title: string;
  /** country code of the row, or WORLD */
  iso3: string;
  scope: string;
  source: string;
  /** levels in words ("state, county") or the unit word ("points") */
  levels: string;
  fresh: string;
  /** the layer the (i) button describes: the coarsest of an indicator */
  infoLayer: LayerEntry;
  indicator?: Indicator;
  layer?: LayerEntry;
}

function sourceOf(meta: Meta | undefined): string {
  const s = meta?.sources.find((x) => x.role === 'primary') ?? meta?.sources[0];
  return s?.publisher ?? '';
}

/** display.map = false: the layer is not an item of the map (SPEC_DC_world_v0_2_0 4.3); its files, /data and citation stay. */
export function onMap(meta: Meta | undefined): boolean {
  return meta?.display?.map !== false;
}

/** Rows of all topics: one per indicator (fills) and one per point or line layer, world rows first in a topic. */
export function buildRows(world: CountryModel | null, countries: CountryModel[], metas: Record<string, Meta>): PanelRow[] {
  const rows: PanelRow[] = [];
  for (const m of world ? [world, ...countries] : countries) {
    const scope = m.iso3 === WORLD ? 'World' : m.name;
    for (const ind of m.indicators) {
      const first = ind.levels[0].layer;
      const meta = metas[first.meta_id];
      if (!onMap(meta)) continue;
      rows.push({
        key: ind.key,
        kind: 'fill',
        topic: topicFor(first, meta),
        title: ind.title,
        iso3: m.iso3,
        scope,
        source: sourceOf(meta),
        levels: capitalize(ind.levels.map((x) => unitWord(x.layer)).join(', ')),
        fresh: throughLabel(meta),
        infoLayer: first,
        indicator: ind,
      });
    }
    for (const l of m.overlays) {
      const meta = metas[l.meta_id];
      if (!onMap(meta)) continue;
      rows.push({
        key: l.layer_id,
        kind: 'overlay',
        topic: topicFor(l, meta),
        title: indicatorTitle(l, meta),
        iso3: m.iso3,
        scope,
        source: sourceOf(meta),
        levels: capitalize(unitWord(l)),
        fresh: throughLabel(meta),
        infoLayer: l,
        layer: l,
      });
    }
  }
  return rows;
}

/** Non-empty topics in the fixed order, each with its rows (world rows first, then the input order). */
export function rowsByTopic(rows: PanelRow[]): { topic: Topic; rows: PanelRow[] }[] {
  return TOPICS.map((topic) => {
    const mine = rows.filter((r) => r.topic === topic);
    return { topic, rows: [...mine.filter((r) => r.iso3 === WORLD), ...mine.filter((r) => r.iso3 !== WORLD)] };
  }).filter((t) => t.rows.length > 0);
}

