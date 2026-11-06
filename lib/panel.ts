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

/** A point or line layer of a family with the scope (WORLD or a country) it belongs to. */
export interface FamilyOverlay {
  layer: LayerEntry;
  iso3: string;
}

/**
 * A row of the panel is a FAMILY of layers (SPEC_WEB_territory r9 16): the layers of one source and one topic,
 * whatever their scope (world or country) and geometry. Key: display.series, otherwise the title without its last
 * " · " fragment. A row has at most two switches: points (or lines) and colors.
 */
export interface PanelRow {
  key: string;
  topic: Topic;
  title: string;
  /** WORLD if the family has a layer of the whole world, otherwise the country of its first layer */
  iso3: string;
  scope: string;
  source: string;
  fresh: string;
  /** the layer the (i) button describes */
  infoLayer: LayerEntry;
  /** display.tags of the layers: extra words for the search */
  tags: string[];
  /** words of the levels and units, for the search only */
  words: string;
  /** the fills of the family (one indicator per country or for the world), only layers that are on the map */
  fills: Indicator[];
  /** the points and lines of the family that are on the map */
  overlays: FamilyOverlay[];
}

function sourceOf(meta: Meta | undefined): string {
  const s = meta?.sources.find((x) => x.role === 'primary') ?? meta?.sources[0];
  return s?.publisher ?? '';
}

/** display.map = false: the layer is not an item of the map (SPEC_DC_world_v0_2_0 4.3); its files, /data and citation stay. */
export function onMap(meta: Meta | undefined): boolean {
  return meta?.display?.map !== false;
}

/** The word of the second switch: Lines if every point-or-line layer of the family is a line, otherwise Points. */
export function overlayWord(row: PanelRow): string {
  return row.overlays.length > 0 && row.overlays.every((o) => o.layer.tiles.geometry_type === 'line') ? 'Lines' : 'Points';
}

/** Does the family have a layer in this country (a fill or a point or line layer of that country)? */
export function inCountry(row: PanelRow, iso3: string): boolean {
  return row.fills.some((i) => i.iso3 === iso3) || row.overlays.some((o) => o.iso3 === iso3);
}

/**
 * The fill the Colors switch turns on: the one of the chosen country, else the world one, else the first.
 * null when the family has no fill.
 */
export function colorsOf(row: PanelRow, country: string | null): Indicator | null {
  return (country ? row.fills.find((i) => i.iso3 === country) : undefined) ?? row.fills.find((i) => i.iso3 === WORLD) ?? row.fills[0] ?? null;
}

/** Rows of all topics: one per family, in the order the families first appear (world models first). */
export function buildRows(world: CountryModel | null, countries: CountryModel[], metas: Record<string, Meta>): PanelRow[] {
  const rows: PanelRow[] = [];
  const get = (key: string, layer: LayerEntry, meta: Meta, iso3: string): PanelRow => {
    let r = rows.find((x) => x.key === key);
    if (!r) {
      r = {
        key,
        topic: topicFor(layer, meta),
        title: key,
        iso3,
        scope: '',
        source: sourceOf(meta),
        fresh: throughLabel(meta),
        infoLayer: layer,
        tags: [],
        words: '',
        fills: [],
        overlays: [],
      };
      rows.push(r);
    }
    return r;
  };
  const names = new Map<string, string[]>();
  const note = (key: string, iso3: string, name: string) => {
    const a = names.get(key) ?? [];
    const label = iso3 === WORLD ? 'World' : name;
    if (!a.includes(label)) a.push(label);
    names.set(key, a);
  };
  for (const m of world ? [world, ...countries] : countries) {
    for (const ind of m.indicators) {
      const first = ind.levels[0].layer;
      const meta = metas[first.meta_id];
      if (!onMap(meta)) continue;
      const r = get(ind.title, first, meta, m.iso3);
      if (m.iso3 === WORLD) r.iso3 = WORLD;
      r.fills.push(ind);
      r.words += ` ${ind.levels.map((x) => unitWord(x.layer)).join(' ')}`;
      for (const t of meta?.display?.tags ?? []) if (!r.tags.includes(t)) r.tags.push(t);
      note(ind.title, m.iso3, m.name);
    }
    for (const l of m.overlays) {
      const meta = metas[l.meta_id];
      if (!onMap(meta)) continue;
      const r = get(indicatorTitle(l, meta), l, meta, m.iso3);
      if (m.iso3 === WORLD) r.iso3 = WORLD;
      r.overlays.push({ layer: l, iso3: m.iso3 });
      r.words += ` ${unitWord(l)}`;
      for (const t of meta?.display?.tags ?? []) if (!r.tags.includes(t)) r.tags.push(t);
      note(indicatorTitle(l, meta), m.iso3, m.name);
    }
  }
  for (const r of rows) {
    r.scope = r.iso3 === WORLD ? 'World' : (names.get(r.key) ?? []).join(', ');
    r.words = capitalize(r.words.trim());
    // The (i) button describes the layer that gives the family its place on the map: a world one first
    const world0 = r.overlays.find((o) => o.iso3 === WORLD)?.layer ?? r.fills.find((i) => i.iso3 === WORLD)?.levels[0].layer;
    r.infoLayer = world0 ?? r.fills[0]?.levels[0].layer ?? r.overlays[0]?.layer ?? r.infoLayer;
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


/** Rows whose title, source, topic, scope, levels or tags contain every word of the query (the first few). */
export function searchRows(rows: PanelRow[], query: string, limit = 6): PanelRow[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  const hay = (r: PanelRow) => [r.title, r.source, r.topic, r.scope, r.words, ...r.tags].join(' ').toLowerCase();
  return rows.filter((r) => {
    const h = hay(r);
    return words.every((w) => h.includes(w));
  }).slice(0, limit);
}
