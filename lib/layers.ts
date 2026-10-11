// Generic helpers for choosing and grouping layers. Everything comes from the manifest and meta.json:
// no layer ids, country codes or field names here (SPEC_WEB 0.3).
import type { LayerEntry, Meta } from './data';
import { countryNameFromIso3 } from './iso3';

export function countryOf(meta: Meta | undefined): string {
  return meta?.coverage.frame?.iso3 ?? '';
}

export function countryName(meta: Meta | undefined): string {
  const iso = countryOf(meta);
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
 * The meta that tells which country a layer belongs to: its own coverage.frame, or, when it has none
 * (segments and points have no frame), the frame of another layer made from the same source.
 */
function frameMeta(l: LayerEntry, layers: LayerEntry[], metas: Record<string, Meta>): Meta | undefined {
  const own = metas[l.meta_id];
  if (own?.coverage.frame) return own;
  const ids = new Set(own?.sources.map((s) => s.source_id) ?? []);
  for (const o of layers) {
    const m = metas[o.meta_id];
    if (m?.coverage.frame && m.sources.some((s) => ids.has(s.source_id))) return m;
  }
  return own;
}

/** Groups layers by country (order of first appearance), then by domain inside the country. */
export function groupByCountry(layers: LayerEntry[], metas: Record<string, Meta>): CountryGroup[] {
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
  return out;
}

/** Union of layer bboxes, or null if none has one. */
export function unionBbox(layers: LayerEntry[]): [number, number, number, number] | null {
  let b: [number, number, number, number] | null = null;
  for (const l of layers) {
    if (!l.bbox) continue;
    b = b ? [Math.min(b[0], l.bbox[0]), Math.min(b[1], l.bbox[1]), Math.max(b[2], l.bbox[2]), Math.max(b[3], l.bbox[3])] : [...l.bbox];
  }
  return b;
}
