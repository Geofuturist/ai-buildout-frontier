// Filters by the value of a field (display.filters, SPEC_GEM_plants r6 3a Q4 and r7 W6). The reader may tick several
// values; the ticked ones work as "or" (an object with any of them stays); nothing ticked = "All" (V, 01.11):
//  - mode "equals": the field holds one value; the default is ticked at first;
//  - mode "contains": the field holds codes joined by "; "; the match is on a whole code.
// A layer that colours by type (display.color_field with color_classes) also gets a filter by its types.
// Nothing is counted: the choice becomes a filter expression of the map layer.
import type { ExpressionSpecification } from 'maplibre-gl';
import type { DisplayFilter, Meta } from './data';

type Display = NonNullable<Meta['display']>;

/** layer_id -> field -> the chosen values; a field the reader has not touched is absent (its default holds) */
export type LayerFilters = Record<string, Record<string, string[]>>;

/** The filters of the meta, and the filter by type of a layer drawn as squares (the types of the legend). */
export function typeFilterOf(d: Display | undefined): DisplayFilter | null {
  // layers drawn as icons that colour by type and have no filter of their own by type (Atlas has its own)
  if (!d || !d.shape || d.count_field || d.filter_fields || !d.color_field || !d.color_classes?.length) return null;
  return { field: d.color_field, mode: 'equals', default: null, values: d.color_classes.map((c) => ({ value: c, label: d.legend_type_labels?.[c] ?? c })) };
}

export function filtersOf(d: Display | undefined): DisplayFilter[] {
  const own = d?.filters ?? [];
  const t = typeFilterOf(d);
  return t && !own.some((f) => f.field === t.field) ? [t, ...own] : own;
}

export function hasFilters(d: Display | undefined): boolean {
  return filtersOf(d).length > 0;
}

/** Chosen values of every filter of a layer: what the reader set, otherwise the default. */
export function effectiveFilters(d: Display | undefined, saved: Record<string, string[]> | undefined): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const f of filtersOf(d)) {
    out[f.field] = saved?.[f.field] ?? (f.default ? [f.default] : []);
  }
  return out;
}

/** Filter expression of the map layer, or null when everything is shown. */
export function filterExpression(d: Display | undefined, saved: Record<string, string[]> | undefined): ExpressionSpecification | null {
  const chosen = effectiveFilters(d, saved);
  const parts: unknown[] = [];
  for (const f of filtersOf(d)) {
    const vals = chosen[f.field] ?? [];
    if (vals.length === 0) continue;
    if (f.mode === 'equals') {
      parts.push(vals.length === 1 ? ['==', ['get', f.field], vals[0]] : ['match', ['get', f.field], vals, true, false]);
    } else {
      // whole codes only: "; " around both the value and the code
      const hay = ['concat', '; ', ['to-string', ['get', f.field]], '; '];
      parts.push(['any', ...vals.map((v) => ['in', `; ${v}; `, hay])]);
    }
  }
  if (parts.length === 0) return null;
  return (parts.length === 1 ? parts[0] : ['all', ...parts]) as ExpressionSpecification;
}
