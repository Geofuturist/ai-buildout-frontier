// Visual system (SPEC_WEB section 6) and MapLibre expressions built from it.
import type { ExpressionSpecification } from 'maplibre-gl';

export const COLORS = {
  surface: '#fcfcfb',
  water: '#e3e7ea',
  ramp: ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281'],
  // Warm ramp of the energy domain (SPEC_WEB r8 0.5): muted amber to brown, lightest step 2.13:1 on the surface
  rampWarm: ['#e0a458', '#cf8236', '#b1642a', '#8a4a22', '#62331a'],
  zero: '#e0dbd0',
  zeroStroke: '#c9c2b4',
  noValue: '#6b6f76',
  notCovered: '#8a8f96',
  disputedFill: '#e7e3dc',
  disputedLine: '#b9b2a6',
  adm0: '#3a3f45',
  adm1: '#6b7280',
  selected: '#0f6e6e',
  // Data-center points (domain dc): plum, apart from the blue and the warm ramps
  point: '#9c2f7f',
} as const;

export interface VoltageBand {
  id: string;
  label: string;
  color: string;
  width: number;
  dashed?: boolean;
}

// Six voltage steps on the blue ramp (the sixth step is darker than the fill ramp's last one)
export const VOLTAGE_BANDS: VoltageBand[] = [
  { id: 'lt100', label: 'Below 100 kV', color: '#86b6ef', width: 0.6 },
  { id: '100_199', label: '100–199 kV', color: '#5598e7', width: 0.9 },
  { id: '200_299', label: '200–299 kV', color: '#2a78d6', width: 1.2 },
  { id: '300_399', label: '300–399 kV', color: '#1c5cab', width: 1.6 },
  { id: '400_599', label: '400–599 kV', color: '#104281', width: 2.0 },
  { id: 'ge600', label: '600 kV and above', color: '#082a58', width: 2.6 },
  { id: 'dc', label: 'Direct current', color: '#1f8a5b', width: 1.6 },
  { id: 'unknown', label: 'Voltage not recorded', color: '#8a8f96', width: 0.8, dashed: true },
];

/** The class ramp of a layer, chosen by its domain: warm for energy, blue for everything else. */
export function rampFor(domain: string | undefined): readonly string[] {
  return domain === 'energy' ? COLORS.rampWarm : COLORS.ramp;
}

/** Fill colour of a unit layer: no value / zero / five classes (breaks has 4 entries). */
export function fillColorExpression(field: string, breaks: number[], domain?: string): ExpressionSpecification {
  const ramp = rampFor(domain);
  const step: unknown[] = ['step', ['get', field], ramp[0]];
  breaks.forEach((b, i) => step.push(b, ramp[Math.min(i + 1, ramp.length - 1)]));
  return [
    'case',
    ['==', ['get', field], null], COLORS.noValue,
    ['==', ['get', field], 0], COLORS.zero,
    step,
  ] as unknown as ExpressionSpecification;
}

export function bandColorExpression(field: string): ExpressionSpecification {
  const m: unknown[] = ['match', ['get', field]];
  for (const b of VOLTAGE_BANDS) if (b.id !== 'unknown') m.push(b.id, b.color);
  m.push(VOLTAGE_BANDS[VOLTAGE_BANDS.length - 1].color);
  return m as unknown as ExpressionSpecification;
}

/** Line width by band and zoom; `extra` widens it (used for the casing under the lines). */
export function bandWidthExpression(field: string, extra = 0): ExpressionSpecification {
  const m: unknown[] = ['match', ['get', field]];
  for (const b of VOLTAGE_BANDS) if (b.id !== 'unknown') m.push(b.id, b.width);
  m.push(VOLTAGE_BANDS[VOLTAGE_BANDS.length - 1].width);
  return ['interpolate', ['linear'], ['zoom'], 3, ['+', ['*', m, 0.6], extra], 9, ['+', ['*', m, 1.6], extra]] as unknown as ExpressionSpecification;
}

export interface LegendClass {
  label: string;
  color: string;
}

/** Legend classes for a county layer. */
export function legendClasses(breaks: number[], unit: string, zeroClass: boolean, domain?: string): LegendClass[] {
  const ramp = rampFor(domain);
  const fmt = (n: number) => n.toLocaleString('en-US');
  const out: LegendClass[] = [];
  if (zeroClass) out.push({ label: '0 — none listed in the source', color: COLORS.zero });
  const first = breaks[0];
  out.push({ label: zeroClass ? `Above 0 – ${fmt(first)} ${unit}` : `Below ${fmt(first)} ${unit}`, color: ramp[0] });
  for (let i = 0; i < breaks.length - 1; i++) {
    out.push({ label: `${fmt(breaks[i])} – ${fmt(breaks[i + 1])} ${unit}`, color: ramp[i + 1] });
  }
  out.push({ label: `${fmt(breaks[breaks.length - 1])} ${unit} and above`, color: ramp[breaks.length] });
  return out;
}
