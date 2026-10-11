// Visual system (SPEC_WEB section 6) and MapLibre expressions built from it.
import type { ExpressionSpecification } from 'maplibre-gl';

export const COLORS = {
  surface: '#fcfcfb',
  water: '#e3e7ea',
  ramp: ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281'],
  zero: '#e0dbd0',
  zeroStroke: '#c9c2b4',
  noValue: '#6b6f76',
  notCovered: '#8a8f96',
  disputedFill: '#e7e3dc',
  disputedLine: '#b9b2a6',
  adm0: '#3a3f45',
  adm1: '#6b7280',
  selected: '#0f6e6e',
  point: '#2b2f36',
} as const;

export interface VoltageBand {
  id: string;
  label: string;
  color: string;
  width: number;
  dashed?: boolean;
}

export const VOLTAGE_BANDS: VoltageBand[] = [
  { id: 'lt100', label: 'Below 100 kV', color: '#f78955', width: 0.6 },
  { id: '100_199', label: '100–199 kV', color: '#df733e', width: 0.9 },
  { id: '200_299', label: '200–299 kV', color: '#c65d26', width: 1.2 },
  { id: '300_399', label: '300–399 kV', color: '#af4803', width: 1.6 },
  { id: '400_599', label: '400–599 kV', color: '#973200', width: 2.0 },
  { id: 'ge600', label: '600 kV and above', color: '#7a2400', width: 2.6 },
  { id: 'dc', label: 'Direct current', color: '#4a3aa7', width: 1.6 },
  { id: 'unknown', label: 'Voltage not recorded', color: '#8a8f96', width: 0.8, dashed: true },
];

/** Fill colour of a county layer: no value / zero / five classes (breaks has 4 entries). */
export function fillColorExpression(field: string, breaks: number[]): ExpressionSpecification {
  const step: unknown[] = ['step', ['get', field], COLORS.ramp[0]];
  breaks.forEach((b, i) => step.push(b, COLORS.ramp[Math.min(i + 1, COLORS.ramp.length - 1)]));
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

export function bandWidthExpression(field: string): ExpressionSpecification {
  const m: unknown[] = ['match', ['get', field]];
  for (const b of VOLTAGE_BANDS) if (b.id !== 'unknown') m.push(b.id, b.width);
  m.push(VOLTAGE_BANDS[VOLTAGE_BANDS.length - 1].width);
  return ['interpolate', ['linear'], ['zoom'], 3, ['*', m, 0.6], 9, ['*', m, 1.6]] as unknown as ExpressionSpecification;
}

export interface LegendClass {
  label: string;
  color: string;
}

/** Legend classes for a county layer. */
export function legendClasses(breaks: number[], unit: string, zeroClass: boolean): LegendClass[] {
  const fmt = (n: number) => n.toLocaleString('en-US');
  const out: LegendClass[] = [];
  if (zeroClass) out.push({ label: '0 — none listed in the source', color: COLORS.zero });
  const first = breaks[0];
  out.push({ label: zeroClass ? `Above 0 – ${fmt(first)} ${unit}` : `Below ${fmt(first)} ${unit}`, color: COLORS.ramp[0] });
  for (let i = 0; i < breaks.length - 1; i++) {
    out.push({ label: `${fmt(breaks[i])} – ${fmt(breaks[i + 1])} ${unit}`, color: COLORS.ramp[i + 1] });
  }
  out.push({ label: `${fmt(breaks[breaks.length - 1])} ${unit} and above`, color: COLORS.ramp[breaks.length] });
  return out;
}
