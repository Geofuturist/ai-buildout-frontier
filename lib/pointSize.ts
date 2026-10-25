// Sized points (display.size_field, SPEC_DC_world 6 and 14): radius by class, a mark for 0 and for "unknown".
// Expressions only: nothing here knows a layer id or a field name; the field comes from display.size_field.
import type { ExpressionSpecification } from 'maplibre-gl';
import type { Meta } from './data';

/** Radii in px of the four classes (below the first break ... above the last). */
export const SIZE_RADII = [3.5, 5, 7, 10];
export const UNKNOWN_RADIUS = 3;
export const UNKNOWN_COLOR = '#8a8f96';
/** A field of classes (display.size_classes) and a numeric field are two different bases: two colours. */
export const CLASS_COLOR = '#9c2f7f';
export const NUMBER_COLOR = '#1f8a4c';
/** light ring around a point: px outside the dot */
export const RING_EXTRA = 2.4;
// Position and capacity status are contract fields of every point layer (ADR 6.2)
const STATUS_FIELD = 'power_status';

type Display = NonNullable<Meta['display']>;

export function isSized(d: Display | undefined): d is Display & { size_field: string } {
  return Boolean(d?.size_field);
}

/** true when the size field holds classes (strings), false when it holds numbers */
export function isClassField(d: Display): boolean {
  return Boolean(d.size_classes && d.size_classes.length > 0);
}

export function colorOf(d: Display): string {
  return isClassField(d) ? CLASS_COLOR : NUMBER_COLOR;
}

/** The value of the source is missing or withheld: the point stays on the map as a small grey dot. */
export function unknownCondition(d: Display & { size_field: string }): ExpressionSpecification {
  return ['any', ['!', ['has', d.size_field]], ['==', ['get', STATUS_FIELD], 'not_found'], ['==', ['get', STATUS_FIELD], 'withheld']] as ExpressionSpecification;
}

/** Numeric field with zero_class: 0 is a value of the source, drawn as a hollow ring. */
export function zeroCondition(d: Display & { size_field: string }): ExpressionSpecification | null {
  if (isClassField(d) || !d.zero_class) return null;
  return ['==', ['to-number', ['get', d.size_field], -1], 0] as ExpressionSpecification;
}

export function radiusExpression(d: Display & { size_field: string }): ExpressionSpecification {
  let by: unknown;
  if (isClassField(d)) {
    const m: unknown[] = ['match', ['get', d.size_field]];
    (d.size_classes ?? []).forEach((c, i) => m.push(c, SIZE_RADII[Math.min(i, SIZE_RADII.length - 1)]));
    m.push(UNKNOWN_RADIUS);
    by = m;
  } else {
    const s: unknown[] = ['step', ['to-number', ['get', d.size_field], 0], SIZE_RADII[0]];
    (d.size_breaks ?? []).forEach((b, i) => s.push(b, SIZE_RADII[Math.min(i + 1, SIZE_RADII.length - 1)]));
    by = s;
  }
  return ['case', unknownCondition(d), UNKNOWN_RADIUS, by] as unknown as ExpressionSpecification;
}

// ---- Places with several records: a badge with the number (display.count_field, display.count_breaks) ----
// The number is a value of the published layer: nothing is counted in the browser.

/** Radii in px of the badge classes (first class ... last); a layer with more classes reuses the last one. */
export const BADGE_RADII = [11, 15, 19];
export const BADGE_TEXT_SIZES = [11, 12.5, 14];
export const BADGE_COLOR = '#3f4752';

export type Counted = Display & { count_field: string; count_breaks: number[] };

export function isCounted(d: Display | undefined): d is Counted {
  return Boolean(d?.count_field && d.count_breaks && d.count_breaks.length > 0);
}

/** true where the place has at least `count_breaks[0]` records: a badge. Below it the place is a point by size_field. */
export function badgeCondition(d: Counted): ExpressionSpecification {
  return ['>=', ['to-number', ['get', d.count_field], 0], d.count_breaks[0]] as unknown as ExpressionSpecification;
}

/** A value per badge class (the first below the second break, and so on), as a MapLibre step on the count field. */
function stepByCount(d: Counted, values: number[], field: string = d.count_field): ExpressionSpecification {
  const s: unknown[] = ['step', ['to-number', ['get', field], 0], values[0]];
  d.count_breaks.slice(1).forEach((b, i) => s.push(b, values[Math.min(i + 1, values.length - 1)]));
  return s as unknown as ExpressionSpecification;
}

export function badgeRadius(d: Counted, field?: string): ExpressionSpecification {
  return stepByCount(d, BADGE_RADII, field);
}

export function badgeTextSize(d: Counted, field?: string): ExpressionSpecification {
  return stepByCount(d, BADGE_TEXT_SIZES, field);
}

/** Radius of a place on the map: the badge class, or the size class of its one record. `field` replaces the count (filter by type). */
export function placeRadius(d: Counted & { size_field: string }, field?: string): ExpressionSpecification {
  return ['case', badgeCondition(d), badgeRadius(d, field), radiusExpression(d)] as unknown as ExpressionSpecification;
}

// ---- Colour by type (display.color_field, display.color_classes) and the filter by type (display.filter_fields) ----
// Six colours and grey, picked to stay apart for readers with colour-vision deficiency (Okabe-Ito set); none is green,
// because green belongs to the numeric-size points. Classes are taken in the order of the legend; any class after the
// sixth is grey. The stroke of the yellow is darker so that it shows on a light map.
export const TYPE_PALETTE: { fill: string; stroke: string }[] = [
  { fill: '#0072B2', stroke: '#0072B2' }, // blue
  { fill: '#E69F00', stroke: '#E69F00' }, // orange
  { fill: '#CC79A7', stroke: '#CC79A7' }, // reddish purple
  { fill: '#56B4E9', stroke: '#56B4E9' }, // sky blue
  { fill: '#F0E442', stroke: '#A39A00' }, // yellow
  { fill: '#D55E00', stroke: '#D55E00' }, // vermillion
];
export const TYPE_GREY = { fill: UNKNOWN_COLOR, stroke: UNKNOWN_COLOR };

export type Typed = Display & { color_field: string; color_classes: string[] };

export function isTyped(d: Display | undefined): d is Typed {
  return Boolean(d?.color_field && d.color_classes && d.color_classes.length > 0);
}

export function typeColor(index: number): { fill: string; stroke: string } {
  return TYPE_PALETTE[index] ?? TYPE_GREY;
}

/** Colour of a point by the value of color_field (fill or stroke). */
export function typeColorExpression(d: Typed, part: 'fill' | 'stroke'): ExpressionSpecification {
  const m: unknown[] = ['match', ['get', d.color_field]];
  d.color_classes.forEach((c, i) => m.push(c, typeColor(i)[part]));
  m.push(TYPE_GREY[part]);
  return m as unknown as ExpressionSpecification;
}

/** The column of the chosen group, if the layer has the filter and knows the group. */
export function filterColumn(d: Display, group: string | null): string | null {
  return group && isTyped(d) && d.filter_fields?.[group] ? d.filter_fields[group] : null;
}

/**
 * What is shown when one group is chosen: places with several records that have at least one record of the group
 * (number and size from that group's column), and places with one record of the group. Values come from the tiles.
 */
export function groupShown(d: Counted & Typed, group: string, column: string): ExpressionSpecification {
  return [
    'any',
    ['all', badgeCondition(d), ['>', ['to-number', ['get', column], 0], 0]],
    ['all', ['!', badgeCondition(d)], ['==', ['get', d.color_field], group]],
  ] as unknown as ExpressionSpecification;
}

/** Labels of the badge classes from the thresholds: "2–9 records", "10 records and above". */
export function countLabels(breaks: number[], noun = 'records'): string[] {
  const f = (n: number) => n.toLocaleString('en-US');
  return breaks.map((b, i) => {
    if (i === breaks.length - 1) return `${f(b)} ${noun} and above`;
    const hi = breaks[i + 1] - 1;
    return hi === b ? `${f(b)} ${noun}` : `${f(b)}–${f(hi)} ${noun}`;
  });
}

/** Labels of the size classes from the thresholds: "Below 10 MW", "10–99 MW", ..., "1,000 MW and above". */
export function sizeLabels(breaks: number[], unit: string): string[] {
  const f = (n: number) => n.toLocaleString('en-US');
  const u = unit ? ` ${unit}` : '';
  const out = [`Below ${f(breaks[0])}${u}`];
  for (let i = 0; i < breaks.length - 1; i++) out.push(`${f(breaks[i])}–${f(breaks[i + 1] - 1)}${u}`);
  out.push(`${f(breaks[breaks.length - 1])}${u} and above`);
  return out;
}
