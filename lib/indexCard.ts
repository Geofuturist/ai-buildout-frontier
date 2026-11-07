// Territory card: totals of the records of a unit, read from the published territory index (abf-index; SPEC_INDEX_territory
// r5 §4, SPEC_WEB_territory r12 §17 item 2). The site adds up only what the index declares additive in meta.json
// "aggregations": counts of records, and a field's sum only within the fields named by "within"; a distinct count
// (stations) is never carried up the chain. Nothing is added across layers. No layer, country or field name is known here:
// every name comes from the index meta and from content/site.json.

import { splitFields } from './csv';

/** meta.json of one index set, as the site keeps it (files reduced to the country codes) */
export interface IndexSetMeta {
  aggregations: Record<string, Agg>;
  levels_by_country: Record<string, { adm1: boolean; adm2: boolean }>;
  layers: Record<string, number>;
  /** country codes that have a file */
  countries: string[];
  index_version: string;
}

export interface Agg {
  layer_id?: string;
  by?: string[];
  count?: string;
  note?: string;
  count_distinct?: string;
  additive_up_the_chain?: boolean;
  /** nested sum (an entry with a layer), or a top-level sum entry that has field + within */
  sum?: { field: string; within?: string[]; only?: string; label?: string };
  field?: string;
  within?: string[];
}

export type Row = Record<string, string>;

export function parseRows(header: string, rows: string[]): Row[] {
  const cols = splitFields(header);
  return rows.map((raw) => {
    const v = splitFields(raw);
    const o: Row = {};
    for (let i = 0; i < cols.length; i++) o[cols[i]] = v[i] ?? '';
    return o;
  });
}

/** which column of the index holds a unit of this level */
export const levelColumn = (level: number): 'adm0' | 'adm1' | 'adm2' => (level <= 0 ? 'adm0' : level === 1 ? 'adm1' : 'adm2');

export interface Histogram {
  field: string;
  items: { value: string; n: number }[];
}

export interface Joint {
  fields: string[];
  cells: { values: string[]; n: number; sum: number | null }[];
}

export interface Summary {
  /** the name of the entry in aggregations */
  key: string;
  layer_id: string | null;
  /** the counted word (records, sites, ...) as the index declares it */
  unit: string;
  n: number;
  note?: string;
  hists: Histogram[];
  joint?: Joint;
  /** sum of a field over the whole layer of the unit: only where the index says so ("only") */
  total?: { field: string; label: string; value: number };
  distinct?: { field: string; n: number; additive: boolean };
}

const num = (s: string): number => {
  const x = Number(s);
  return Number.isFinite(x) ? x : 0;
};

function countBy(rows: Row[], field: string): { value: string; n: number }[] {
  const m = new Map<string, number>();
  for (const r of rows) {
    const v = r[field] ?? '';
    m.set(v, (m.get(v) ?? 0) + 1);
  }
  return [...m].map(([value, n]) => ({ value, n })).sort((a, b) => b.n - a.n || a.value.localeCompare(b.value));
}

/**
 * Totals of the rows of one unit by the index's own declaration. A count entry (has "count") is read as: one count of
 * the records of its layer, plus, per field of "by", a count by that field; if a sum is declared over the same fields
 * ("within"), the entry is a cross table of those fields, with the count and the sum in each cell. An entry with
 * "count_distinct" is a distinct count that is not added up the chain.
 */
export function summarize(meta: Pick<IndexSetMeta, 'aggregations' | 'layers'>, rows: Row[]): Summary[] {
  const out: Summary[] = [];
  const layerIds = Object.keys(meta.layers);
  const entries = Object.entries(meta.aggregations);
  // A sum entry of the top level (field + within) belongs to the count entry that has the same fields in "by"
  const topSums = entries.filter(([, e]) => e.field && e.within).map(([, e]) => e);
  const layerOf = (e: Agg): string | null => e.layer_id ?? (layerIds.length === 1 ? layerIds[0] : null);
  const rowsOf = (lid: string | null) => (lid ? rows.filter((r) => r.layer_id === lid) : rows);

  for (const [key, e] of entries) {
    if (e.count) {
      const lid = layerOf(e);
      const mine = rowsOf(lid);
      const s: Summary = { key, layer_id: lid, unit: e.count, n: mine.length, note: e.note, hists: [] };
      const by = e.by ?? [];
      const sumSpec = e.sum && e.sum.within ? e.sum : topSums.find((t) => t.within && t.within.length === by.length && t.within.every((f, i) => f === by[i]));
      const sumField = sumSpec ? (sumSpec.field ?? (sumSpec as unknown as Agg).field) : null;
      if (sumSpec && by.length > 0) {
        const m = new Map<string, { values: string[]; n: number; sum: number }>();
        for (const r of mine) {
          const values = by.map((f) => r[f] ?? '');
          const k = values.join('\u0001');
          const c = m.get(k) ?? { values, n: 0, sum: 0 };
          c.n++;
          c.sum += sumField ? num(r[sumField]) : 0;
          m.set(k, c);
        }
        s.joint = { fields: by, cells: [...m.values()].sort((a, b) => b.sum - a.sum || b.n - a.n) };
      } else {
        s.hists = by.map((f) => ({ field: f, items: countBy(mine, f) }));
      }
      if (e.sum && e.sum.only && !e.sum.within) {
        const only = rowsOf(e.sum.only);
        s.total = { field: e.sum.field, label: e.sum.label ?? e.sum.field, value: only.reduce((a, r) => a + num(r[e.sum!.field]), 0) };
      }
      out.push(s);
    } else if (e.count_distinct) {
      const lid = layerOf(e);
      const mine = rowsOf(lid);
      const set = new Set(mine.map((r) => r[e.count_distinct!]).filter(Boolean));
      out.push({ key, layer_id: lid, unit: e.count_distinct, n: mine.length, hists: [], distinct: { field: e.count_distinct, n: set.size, additive: e.additive_up_the_chain === true } });
    }
  }
  return out;
}

export type Basis = 'point' | 'field' | 'mixed' | 'none';

/** the basis of the assignment of a layer's rows at the level of the unit */
export function basisOf(rows: Row[], level: number): Basis {
  const col = level <= 0 ? 'adm0_basis' : 'unit_basis';
  let f = 0;
  let p = 0;
  for (const r of rows) {
    if (r[col] === 'field') f++;
    else if (r[col] === 'point') p++;
  }
  if (f && p) return 'mixed';
  if (f) return 'field';
  if (p) return 'point';
  return 'none';
}

export const approximateCount = (rows: Row[]): number => rows.filter((r) => r.approximate === 'true').length;

/** rows with a unit_note, counted by note: why the record has no unit at the first level that the country has */
export function noteCounts(rows: Row[]): { note: string; n: number }[] {
  return countBy(rows.filter((r) => r.unit_note), 'unit_note').map(({ value, n }) => ({ note: value, n }));
}

/**
 * Records that the source lists under another country, from adm0_other.csv (all rows with adm0_other). For a country X:
 * - here: records that lie in X but that the source lists elsewhere;
 * - away: records the source lists under X that lie in another country.
 * adm0_basis tells which of adm0 and adm0_other is the source's country (field: adm0 is the source's; point: adm0 is
 * the country of the point). For a unit below the country only the point side exists (adm1_point / adm2_point).
 */
export function crossCounts(other: Row[], iso3: string, unitId: string, level: number): { here: number; away: number } {
  let here = 0;
  let away = 0;
  for (const r of other) {
    if (r.adm0_basis === 'field') {
      if (level <= 0 ? r.adm0_other === iso3 : r.adm1_point === unitId || r.adm2_point === unitId) here++;
      if (level <= 0 && r.adm0 === iso3) away++;
    } else {
      if (level <= 0 ? r.adm0 === iso3 : false) here++;
      if (level <= 0 && r.adm0_other === iso3) away++;
    }
  }
  return { here, away };
}

/** records whose unit is below the country but empty although the country has the level (counted for the country only) */
export function countryOnly(rows: Row[], hasAdm1: boolean): number {
  return hasAdm1 ? rows.filter((r) => !r.adm1).length : 0;
}

export const fillTemplate = (t: string, v: Record<string, string | number>): string => t.replace(/\{(\w+)\}/g, (m, k) => (k in v ? String(v[k]) : m));

/** thousands with a comma from 1,000, as in every published text (RES_texts_INDEX r4 4) */
export const fmtInt = (n: number): string => n.toLocaleString('en-US');
export const fmtMw = (n: number): string => `${n.toLocaleString('en-US', { maximumFractionDigits: n < 100 ? 1 : 0 })} MW`;
