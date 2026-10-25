// Cards of the Data page (SPEC_WEB_territory 15): one card for each indicator (the layers of one source and one country,
// one per level), each point or line layer, and each boundaries dataset. Everything comes from the manifests and
// meta.json; no layer ids, country codes or topics are named here. Pure functions, safe on server and client.
import type { AbfData, FileRef, LayerEntry, Meta } from './data';
import { doiUrl, throughLabel } from './format';
import { buildCountries } from './indicators';
import { WORLD, capitalize, groupByCountry, unitWord } from './layers';
import { TOPICS, topicFor } from './panel';

export const BOUNDARIES_TOPIC = 'Boundaries';
export type CardTopic = (typeof TOPICS)[number] | typeof BOUNDARIES_TOPIC;

export interface CardFile {
  /** CSV, GeoParquet, ... */
  label: string;
  url: string;
  bytes: number;
  sha256: string;
  name: string;
}

export interface CardPart {
  layerId: string;
  /** "State level", "county", ... */
  title: string;
  files: CardFile[];
}

export interface DataCard {
  key: string;
  title: string;
  topic: CardTopic;
  /** WORLD or an ISO3 code */
  iso3: string;
  scope: string;
  levels: string;
  source: string;
  through: string;
  license: { name: string; url: string };
  dataset: { name: string; version: string; doi: string | null; doiUrl: string | null };
  parts: CardPart[];
  /** reference files of the dataset that belong to the layers of this card */
  extra: CardFile[];
  citation: string;
  /** methodology anchor, if any */
  anchor: string | null;
}

const FORMAT_LABEL: Record<string, string> = { csv: 'CSV', parquet: 'GeoParquet', 'geojson.gz': 'GeoJSON (gzip)', pmtiles: 'Map tiles (display only)' };
const FORMAT_ORDER = ['csv', 'parquet', 'geojson.gz', 'pmtiles'];

const fileOf = (label: string, f: FileRef): CardFile => ({ label, url: f.url, bytes: f.bytes, sha256: f.sha256, name: f.path.split('/').pop() ?? f.path });

function partOf(l: LayerEntry, title: string): CardPart {
  return { layerId: l.layer_id, title, files: FORMAT_ORDER.filter((f) => l.files[f]).map((f) => fileOf(FORMAT_LABEL[f], l.files[f])) };
}

function sourceOf(meta: Meta | undefined): string {
  const s = meta?.sources.find((x) => x.role === 'primary') ?? meta?.sources[0];
  return s?.publisher ?? '';
}

/** Lower-case words of the levels, e.g. "state, county" or "points". */
function levelsOf(layers: LayerEntry[]): string {
  return capitalize(layers.map((l) => unitWord(l)).join(', '));
}

function cardOf(
  data: Pick<AbfData, 'datasets' | 'metas' | 'anchors'>,
  key: string, title: string, topic: CardTopic, iso3: string, scope: string, layers: LayerEntry[], parts: CardPart[],
): DataCard {
  const first = layers[0];
  const meta = data.metas[first.meta_id];
  const ds = data.datasets[first.dataset];
  return {
    key, title, topic, iso3, scope,
    levels: levelsOf(layers),
    source: sourceOf(meta),
    through: throughLabel(meta),
    license: { name: meta.license.name, url: meta.license.url },
    dataset: { name: ds.dataset, version: ds.version, doi: ds.doi, doiUrl: doiUrl(ds.doi) },
    parts,
    extra: layers.flatMap((l) => l.extra_files).map((f) => fileOf(f.description ?? 'Reference file', f)),
    citation: meta.citation.text,
    anchor: data.anchors[first.layer_id] ?? null,
  };
}

/** All cards, ordered: topics in the fixed order, boundaries last; inside a topic the world cards, then countries by name. */
export function buildCards(data: Pick<AbfData, 'datasets' | 'layers' | 'metas' | 'anchors' | 'default_layer'>): DataCard[] {
  const dataLayers = data.layers.filter((l) => data.datasets[l.dataset]?.kind === 'layers');
  const cards: DataCard[] = [];
  const groups = groupByCountry(dataLayers, data.metas, data.default_layer);
  for (const m of buildCountries(groups, data.metas, (l) => l.tiles.geometry_type === 'polygon')) {
    const scope = m.iso3 === WORLD ? 'World' : m.name;
    for (const ind of m.indicators) {
      const layers = ind.levels.map((x) => x.layer);
      const first = layers[0];
      const single = layers.length === 1;
      cards.push(cardOf(
        data, `${m.iso3}:${ind.key}`, single ? first.title : ind.title, topicFor(first, data.metas[first.meta_id]), m.iso3, scope, layers,
        layers.map((l) => partOf(l, single ? 'Files' : `${capitalize(unitWord(l))} level`)),
      ));
    }
    for (const l of m.overlays) {
      cards.push(cardOf(data, `${m.iso3}:${l.layer_id}`, l.title, topicFor(l, data.metas[l.meta_id]), m.iso3, scope, [l], [partOf(l, 'Files')]));
    }
  }
  // Boundaries: one card for each boundaries dataset, a part for each of its layers
  for (const name of Object.keys(data.datasets).filter((n) => data.datasets[n].kind !== 'layers').sort()) {
    const layers = data.layers.filter((l) => l.dataset === name);
    if (layers.length === 0) continue;
    const title = data.metas[layers[0].meta_id]?.title ?? name;
    cards.push(cardOf(data, `${WORLD}:${name}`, title, BOUNDARIES_TOPIC, WORLD, 'World', layers, layers.map((l) => partOf(l, l.title))));
  }
  const rank = (t: CardTopic) => (t === BOUNDARIES_TOPIC ? TOPICS.length : TOPICS.indexOf(t));
  return cards
    .map((c, i) => ({ c, i }))
    .sort((a, b) => rank(a.c.topic) - rank(b.c.topic) || Number(b.c.iso3 === WORLD) - Number(a.c.iso3 === WORLD) || (a.c.iso3 === WORLD ? 0 : a.c.scope.localeCompare(b.c.scope, 'en')) || a.i - b.i)
    .map((x) => x.c);
}

/** Non-empty topics in order. */
export function topicsOf(cards: DataCard[]): CardTopic[] {
  return ([...TOPICS, BOUNDARIES_TOPIC] as CardTopic[]).filter((t) => cards.some((c) => c.topic === t));
}

/** Countries that have cards of their own (not the world and not boundaries), with the number of their cards, by name. */
export function countriesOf(cards: DataCard[]): { iso3: string; name: string; n: number }[] {
  const m = new Map<string, { iso3: string; name: string; n: number }>();
  for (const c of cards) {
    if (c.iso3 === WORLD) continue;
    const x = m.get(c.iso3) ?? { iso3: c.iso3, name: c.scope, n: 0 };
    x.n++;
    m.set(c.iso3, x);
  }
  return [...m.values()].sort((a, b) => a.name.localeCompare(b.name, 'en'));
}

/** Datasets of a set of cards with a DOI: one "All files (Zenodo)" link for each dataset. */
export function zenodoLinks(cards: DataCard[]): { name: string; version: string; url: string }[] {
  const seen = new Map<string, { name: string; version: string; url: string }>();
  for (const c of cards) if (c.dataset.doiUrl && !seen.has(c.dataset.name)) seen.set(c.dataset.name, { name: c.dataset.name, version: c.dataset.version, url: c.dataset.doiUrl });
  return [...seen.values()];
}

export function anchorOfTopic(t: string): string {
  return `topic-${t.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}
