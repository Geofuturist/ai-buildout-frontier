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
export const NUMBER_COLOR = '#12408a';
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

/** Labels of the size classes from the thresholds: "Below 10 MW", "10–99 MW", ..., "1,000 MW and above". */
export function sizeLabels(breaks: number[], unit: string): string[] {
  const f = (n: number) => n.toLocaleString('en-US');
  const u = unit ? ` ${unit}` : '';
  const out = [`Below ${f(breaks[0])}${u}`];
  for (let i = 0; i < breaks.length - 1; i++) out.push(`${f(breaks[i])}–${f(breaks[i + 1] - 1)}${u}`);
  out.push(`${f(breaks[breaks.length - 1])}${u} and above`);
  return out;
}
