// lib/queries/datacenters.ts
// Datacenter data fetching functions.
// Pattern: accept SupabaseClient param so page.tsx (Server Component) can pass its
// inline client — avoids the singleton / async init pattern for server-side use.

import type { SupabaseClient } from '@supabase/supabase-js';
import type { FeatureCollection, Point } from 'geojson';

// ─── Types ────────────────────────────────────────────────────────────────────

export type DCStatus =
  | 'operational'
  | 'under_construction'
  | 'planned'
  | 'announced'
  | 'decommissioned'
  | 'unknown';

export type GeocodingPrecision =
  | 'street_level'
  | 'city'
  | 'region'
  | 'country_centroid';

export interface FrontierProps {
  id: string;
  name: string | null;
  owner: string | null;
  country: string | null;
  status: DCStatus;
  power_capacity_mw: number | null;
  h100_equivalent: number | null;
  citation: string | null;
}

export interface ClusterProps {
  id: string;
  name: string | null;
  owner: string | null;
  country: string | null;
  status: DCStatus;
  certainty: string | null;
  power_capacity_mw: number | null;
  h100_equivalent: number | null;
  ops_total: number | null;
  geocoding_precision: GeocodingPrecision | null;
  citation: string | null;
}

export interface OsmProps {
  id: string;
  name: string | null;
  operator: string | null;
}

// ─── Status color palette (shared with Map and DCPopup) ───────────────────────

export const DC_STATUS_COLORS: Record<DCStatus, string> = {
  operational:       '#2563eb', // deep blue
  under_construction: '#f59e0b', // amber
  planned:           '#8b5cf6', // purple
  announced:         '#c084fc', // light purple
  decommissioned:    '#6b7280', // gray
  unknown:           '#94a3b8', // slate
};

// ─── Empty FeatureCollection fallback ────────────────────────────────────────

function emptyFC<P>(): FeatureCollection<Point, P> {
  return { type: 'FeatureCollection', features: [] };
}

// ─── Query functions ──────────────────────────────────────────────────────────

/**
 * Fetch Epoch AI Frontier datacenters (33 spatial records).
 * Falls back to empty FeatureCollection on error — does NOT throw —
 * to avoid breaking the feasibility map if this optional layer is unavailable.
 */
export async function fetchFrontierDCs(
  client: SupabaseClient,
): Promise<FeatureCollection<Point, FrontierProps>> {
  const { data, error } = await client
    .schema('infrastructure')
    .from('datacenters_epoch_frontier')
    .select(
      'id, name, owner, country, status, power_capacity_mw, h100_equivalent, citation, geometry',
    )
    .eq('has_geometry', true);

  if (error) {
    console.error('[fetchFrontierDCs] Supabase error:', error.message);
    return emptyFC<FrontierProps>();
  }

  return {
    type: 'FeatureCollection',
    features: (data ?? []).map((row) => ({
      type: 'Feature' as const,
      geometry: row.geometry as Point,
      properties: {
        id: String(row.id),
        name: row.name ?? null,
        owner: row.owner ?? null,
        country: row.country ?? null,
        status: (row.status ?? 'unknown') as DCStatus,
        power_capacity_mw: row.power_capacity_mw ?? null,
        h100_equivalent: row.h100_equivalent ?? null,
        citation: row.citation ?? null,
      },
    })),
  };
}

/**
 * Fetch Epoch AI GPU Clusters (598 spatial records out of 786 total).
 * Non-spatial records (188) are filtered out by `has_geometry=true`.
 */
export async function fetchClusterDCs(
  client: SupabaseClient,
): Promise<FeatureCollection<Point, ClusterProps>> {
  const { data, error } = await client
    .schema('infrastructure')
    .from('datacenters_epoch_clusters')
    .select(
      'id, name, owner, country, status, certainty, power_capacity_mw, h100_equivalent, ops_total, geocoding_precision, citation, geometry',
    )
    .eq('has_geometry', true);

  if (error) {
    console.error('[fetchClusterDCs] Supabase error:', error.message);
    return emptyFC<ClusterProps>();
  }

  return {
    type: 'FeatureCollection',
    features: (data ?? []).map((row) => ({
      type: 'Feature' as const,
      geometry: row.geometry as Point,
      properties: {
        id: String(row.id),
        name: row.name ?? null,
        owner: row.owner ?? null,
        country: row.country ?? null,
        status: (row.status ?? 'unknown') as DCStatus,
        certainty: row.certainty ?? null,
        power_capacity_mw: row.power_capacity_mw ?? null,
        h100_equivalent: row.h100_equivalent ?? null,
        ops_total: row.ops_total ?? null,
        geocoding_precision: (row.geocoding_precision ?? null) as GeocodingPrecision | null,
        citation: row.citation ?? null,
      },
    })),
  };
}

/**
 * Fetch OpenStreetMap datacenters (US, 1,317 records — all spatial).
 */
export async function fetchOsmDCs(
  client: SupabaseClient,
): Promise<FeatureCollection<Point, OsmProps>> {
  // OSM table has no has_geometry column — all 1,317 records are spatial
  const { data, error } = await client
    .schema('infrastructure')
    .from('datacenters_osm')
    .select('id, name, operator, geometry');

  if (error) {
    console.error('[fetchOsmDCs] Supabase error:', error.message);
    return emptyFC<OsmProps>();
  }

  return {
    type: 'FeatureCollection',
    features: (data ?? []).map((row) => ({
      type: 'Feature' as const,
      geometry: row.geometry as Point,
      properties: {
        id: String(row.id),
        name: row.name ?? null,
        operator: row.operator ?? null,
      },
    })),
  };
}
