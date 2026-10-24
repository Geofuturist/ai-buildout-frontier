// Generic helpers for choosing and grouping layers. Everything comes from the manifest and meta.json:
// no layer ids, country codes or field names here (SPEC_WEB 0.3).
import type { AbfData, LayerEntry, Meta } from './data';
import { countryNameFromIso3 } from './iso3';

/** coverage.iso3 is a string in some metas and a one-item list in others; both are read as one code. */
function firstCode(v: unknown): string {
  const x = Array.isArray(v) ? v[0] : v;
  return typeof x === 'string' ? x : '';
}

/** Pseudo country code of the layers that cover several countries (coverage.iso3 with 2 or more codes). */
export const WORLD = 'WORLD';
/** Below this zoom a click on the globe chooses the whole world (its card offers the world files). */
export const WORLD_ZOOM = 1.2;

export function countryOf(meta: Meta | undefined): string {
  const v = meta?.coverage.iso3;
  if (Array.isArray(v) && v.length >= 2) return WORLD;
  return firstCode(v) || firstCode(meta?.coverage.frame?.iso3);
}

export function countryName(meta: Meta | undefined): string {
  const iso = countryOf(meta);
  if (iso === WORLD) return 'World';
  return meta?.coverage.frame?.country_name ?? (iso ? countryNameFromIso3(iso) : 'Other');
}

const DOMAIN_LABEL: Record<string, string> = { energy: 'Energy', dc: 'Data centers', restrictions: 'Restrictions', observability: 'Observability' };

export function domainLabel(domain: string): string {
  return DOMAIN_LABEL[domain] ?? domain.charAt(0).toUpperCase() + domain.slice(1);
}

/** Last " · " part of a layer title: "county", "department", "segments", "points". */
export function unitWord(layer: LayerEntry): string {
  const parts = layer.title.split('·');
  return parts[parts.length - 1].trim().toLowerCase();
}

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Singular noun for "Download this ..." and record titles: "county", "department", "segment", "point". */
export function recordNoun(layer: LayerEntry): string {
  const w = unitWord(layer);
  return w.endsWith('s') ? w.slice(0, -1) : w;
}

export interface CountryGroup {
  iso3: string;
  name: string;
  domains: { domain: string; layers: LayerEntry[] }[];
}

/**
 * The meta that tells which country a layer belongs to: its own coverage.iso3 (v0.2.0) or coverage.frame.
 * Fallback for v0.1.0, where segments have neither: the country of another layer made from the same source.
 */
function frameMeta(l: LayerEntry, layers: LayerEntry[], metas: Record<string, Meta>): Meta | undefined {
  const own = metas[l.meta_id];
  if (countryOf(own)) return own;
  const ids = new Set(own?.sources.map((s) => s.source_id) ?? []);
  for (const o of layers) {
    const m = metas[o.meta_id];
    if (countryOf(m) && m.sources.some((s) => ids.has(s.source_id))) return m;
  }
  return own;
}

/** The country of a layer (see frameMeta); '' when unknown. */
export function layerCountry(l: LayerEntry, layers: LayerEntry[], metas: Record<string, Meta>): string {
  return countryOf(frameMeta(l, layers, metas));
}

/**
 * Country order (SPEC_WEB 0.3 p.6): the country of the default layer first, the others alphabetically by
 * English name. Nothing depends on the order of datasets in the pointer.
 */
function byDefaultCountryThenName<T extends { iso3: string; name: string }>(items: T[], defaultIso3: string | null): T[] {
  const rank = (x: T) => (defaultIso3 && x.iso3 === defaultIso3 ? 0 : 1);
  return [...items].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, 'en'));
}

/** Groups layers by country, then by domain inside the country; countries ordered as above. */
export function groupByCountry(layers: LayerEntry[], metas: Record<string, Meta>, defaultLayerId: string | null): CountryGroup[] {
  const out: CountryGroup[] = [];
  for (const l of layers) {
    const meta = frameMeta(l, layers, metas);
    const iso3 = countryOf(meta);
    let g = out.find((x) => x.iso3 === iso3);
    if (!g) {
      g = { iso3, name: countryName(meta), domains: [] };
      out.push(g);
    }
    let d = g.domains.find((x) => x.domain === l.domain);
    if (!d) {
      d = { domain: l.domain, layers: [] };
      g.domains.push(d);
    }
    d.layers.push(l);
  }
  const def = defaultLayerId ? layers.find((l) => l.layer_id === defaultLayerId) : undefined;
  return byDefaultCountryThenName(out, def ? layerCountry(def, layers, metas) : null);
}

/**
 * Dataset names in display order (/data, /attribution): datasets of layers first, the dataset of the default
 * layer's country at the top, then alphabetically by country name; the boundaries dataset last.
 */
export function orderedDatasetNames(data: Pick<AbfData, 'datasets' | 'layers' | 'metas' | 'default_layer'>): string[] {
  const dataLayers = data.layers.filter((l) => data.datasets[l.dataset]?.kind === 'layers');
  const def = data.default_layer ? dataLayers.find((l) => l.layer_id === data.default_layer) : undefined;
  const defIso = def ? layerCountry(def, dataLayers, data.metas) : null;
  const info = (name: string) => {
    const first = dataLayers.find((l) => l.dataset === name);
    const meta = first ? frameMeta(first, dataLayers, data.metas) : undefined;
    return { name, iso3: countryOf(meta), label: first ? countryName(meta) : name };
  };
  const layersNames = Object.keys(data.datasets).filter((n) => data.datasets[n].kind === 'layers').map(info);
  const boundaryNames = Object.keys(data.datasets).filter((n) => data.datasets[n].kind !== 'layers').sort();
  const sorted = byDefaultCountryThenName(layersNames.map((x) => ({ ...x, name: x.label, id: x.name })), defIso);
  return [...sorted.map((x) => x.id), ...boundaryNames];
}

/** Union of the home views of the layers: display.home_bbox if the meta has it, otherwise the manifest bbox. */
export function unionBbox(layers: LayerEntry[], metas: Record<string, Meta>): [number, number, number, number] | null {
  let b: [number, number, number, number] | null = null;
  for (const l of layers) {
    const v = metas[l.meta_id]?.display?.home_bbox ?? l.bbox;
    if (!v) continue;
    b = b ? [Math.min(b[0], v[0]), Math.min(b[1], v[1]), Math.max(b[2], v[2]), Math.max(b[3], v[3])] : [...v];
  }
  return b;
}

/** First fragment of a layer title before " · ": "Generation", "Transmission lines" (temporary rule until display.topic). */
export function topicOf(layer: LayerEntry): string {
  return layer.title.split('·')[0].trim().toLowerCase();
}

/** Administrative level as a number: "ADM1" -> 1; unknown levels go last. */
function levelNumber(layer: LayerEntry): number {
  const m = /(\d+)/.exec(layer.level ?? '');
  return m ? Number(m[1]) : 99;
}

/**
 * Which fill layer to switch on when a country is chosen by a click (ARCH 14.10, package 1c).
 * `fills` are the country's fill layers in panel order; `current` is the fill layer that is on now.
 * Same first title fragment as the layer being switched off wins (bigger units first: ADM1 before ADM2);
 * otherwise the first fill layer of the country in panel order. A country's own layer that is already on stays.
 */
export function pickCountryFill(fills: LayerEntry[], current: LayerEntry | undefined): LayerEntry | undefined {
  if (current && fills.some((l) => l.layer_id === current.layer_id)) return current;
  if (current) {
    const topic = topicOf(current);
    const same = fills.filter((l) => topicOf(l) === topic);
    if (same.length) return [...same].sort((a, b) => levelNumber(a) - levelNumber(b))[0];
  }
  return fills[0];
}
