import type { MultiPolygon } from 'geojson';

// ─── Types ────────────────────────────────────────────────────────────────────

export type FeasibilityCategory =
  | 'high_feasibility'
  | 'moderate_feasibility'
  | 'low_feasibility'
  | 'critical_constraint'
  | 'dc_hotspot';

export interface FeasibilityComponents {
  is_dc_hotspot: boolean;
  headroom: {
    headroom_mw: number;
    summer_cap_mw: number;
    net_gen_mwh: number;
    peak_demand_mw: number;
  };
  queue: {
    q_projects: number;
    q_total_mw: number;
    q_realistic_mw: number;
    q_solar_mw: number;
    q_battery_mw: number;
    q_wind_mw: number;
    q_gas_mw: number;
    completion_rate_pct: number;
  };
  substations: {
    sub_critical: number;
    sub_high: number;
    sub_throughput: number;
  };
  feasibility_score: number;
}

export interface RegionWithFeasibility {
  value: number;
  category: FeasibilityCategory;
  components: FeasibilityComponents;
  computed_at: string;
  region: {
    name: string;
    admin_code: string;
    geometry: MultiPolygon;
  };
}

// ─── Color mapping (matches ARCHITECTURE_DECISIONS.md §7.3) ──────────────────

export const FEASIBILITY_COLORS: Record<FeasibilityCategory, string> = {
  high_feasibility:    '#2ecc71',
  moderate_feasibility: '#f1c40f',
  low_feasibility:     '#e67e22',
  critical_constraint: '#e74c3c',
  dc_hotspot:          '#922b21',
};

export const FEASIBILITY_LABELS: Record<FeasibilityCategory, string> = {
  high_feasibility:    'High — grid headroom exceeds queue pressure',
  moderate_feasibility: 'Moderate — balanced',
  low_feasibility:     'Low — constrained',
  critical_constraint: 'Critical — severely constrained',
  dc_hotspot:          'DC Hotspot — local substation exhaustion',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Format a number to 2 decimal places, return '—' for null/undefined */
export function formatMW(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(1)} MW`;
}

/** Format feasibility ratio */
export function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(2);
}

/** Human-readable label for a category */
export function categoryLabel(category: FeasibilityCategory): string {
  return FEASIBILITY_LABELS[category] ?? category;
}
