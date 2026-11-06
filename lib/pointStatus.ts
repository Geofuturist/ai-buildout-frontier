// The kind of status of a point (lib/icons.ts) read from the fields of the object, by the rules of content/site.json
// (status_styles; fetch-data puts them into display.status_style of the layers that have the fields). Expressions only.
import type { ExpressionSpecification } from 'maplibre-gl';
import type { Meta } from './data';
import { FINE_KINDS } from './icons';
import type { Kind, Shape } from './icons';

type Display = NonNullable<Meta['display']>;

export function shapeOf(d: Display | undefined): Shape | null {
  return d?.shape === 'circle' || d?.shape === 'square' ? d.shape : null;
}

/** Kind of the object: by the value of the status field, or by the count columns that stand at 1 (places with one record). */
export function kindExpression(d: Display, zero: ExpressionSpecification | null = null): ExpressionSpecification {
  const st = d.status_style;
  let base: unknown = 'fill';
  if (st?.field && st.values && Object.keys(st.values).length > 0) {
    const m: unknown[] = ['match', ['get', st.field]];
    for (const [v, k] of Object.entries(st.values)) m.push(v, k);
    m.push('fill');
    base = m;
  } else if (st?.counts && st.counts.length > 0) {
    const c: unknown[] = ['case'];
    for (const [f, k] of st.counts) c.push(['>', ['to-number', ['get', f], 0], 0], k);
    c.push('fill');
    base = c;
  }
  // a value of 0 that the source states (Epoch: no power in operation yet) is "not working yet": an outline
  return (zero ? ['case', zero, 'outline', base] : base) as ExpressionSpecification;
}

/** true where the kind is one that needs room (hatch, ?, x) */
export function fineCondition(kind: ExpressionSpecification): ExpressionSpecification {
  return ['match', kind, FINE_KINDS, true, false] as unknown as ExpressionSpecification;
}

/** Kinds a layer can show, in the order of the vocabulary; for the "Status" block of the legend. */
export function kindsOf(d: Display | undefined): Kind[] {
  const st = d?.status_style;
  if (!st) return [];
  const used = new Set<string>(st.values ? Object.values(st.values) : st.counts ? st.counts.map((x) => x[1]) : []);
  return (['fill', 'pale', 'hatch', 'outline', 'q', 'x'] as Kind[]).filter((k) => used.has(k));
}

/** Kind of one record row (the fan of a place): the status field of the records is one of the fields of the rules. */
export function kindOfRow(d: Display | undefined, row: Record<string, unknown>): Kind {
  const st = d?.status_style;
  for (const [field, map] of Object.entries(st?.rowFields ?? {})) {
    const k = map[String(row[field] ?? '')];
    if (k) return k as Kind;
  }
  return 'fill';
}
