// Filters by the value of a field (display.filters, SPEC_GEM_plants r6 3a Q4 and r7 W6):
//  - mode "equals": one value at a time, the default is shown at first;
//  - mode "contains": the field holds codes joined by "; "; the ticked codes work as "or" (an object with any of them
//    stays); nothing ticked = all objects.
// Nothing is counted: the choice becomes a filter expression of the map layer.
import type { ExpressionSpecification } from 'maplibre-gl';
import type { Meta } from './data';

type Display = NonNullable<Meta['display']>;

/** layer_id -> field -> the chosen values; a field the reader has not touched is absent (its default holds) */
export type LayerFilters = Record<string, Record<string, string[]>>;

export function hasFilters(d: Display | undefined): d is Display & { filters: NonNullable<Display['filters']> } {
  return Boolean(d?.filters && d.filters.length > 0);
}

/** Chosen values of every filter of a layer: what the reader set, otherwise the default. */
export function effectiveFilters(d: Display | undefined, saved: Record<string, string[]> | undefined): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const f of d?.filters ?? []) {
    out[f.field] = saved?.[f.field] ?? (f.default ? [f.default] : []);
  }
  return out;
}

/** Filter expression of the map layer, or null when everything is shown. */
export function filterExpression(d: Display | undefined, saved: Record<string, string[]> | undefined): ExpressionSpecification | null {
  const chosen = effectiveFilters(d, saved);
  const parts: unknown[] = [];
  for (const f of d?.filters ?? []) {
    const vals = chosen[f.field] ?? [];
    if (vals.length === 0) continue;
    if (f.mode === 'equals') {
      parts.push(['==', ['get', f.field], vals[0]]);
    } else {
      // whole codes only: "; " around both the value and the code
      const hay = ['concat', '; ', ['to-string', ['get', f.field]], '; '];
      parts.push(['any', ...vals.map((v) => ['in', `; ${v}; `, hay])]);
    }
  }
  if (parts.length === 0) return null;
  return (parts.length === 1 ? parts[0] : ['all', ...parts]) as ExpressionSpecification;
}
