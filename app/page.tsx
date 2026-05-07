// app/page.tsx
// Server Component — fetches all map data in parallel, passes to client AppShell.
// County data joined in JS (PostgREST cross-schema FK limitation — see §3 / §7.2 ADR).
// DC data fetched via query functions that accept the inline client (Arch decision 3).

import { createClient } from '@supabase/supabase-js';
import type { FeatureCollection, Feature, MultiPolygon } from 'geojson';

import Header from './components/Header';
import AppShell from './components/AppShell';
import { fetchFrontierDCs, fetchClusterDCs, fetchOsmDCs } from '@/lib/queries/datacenters';

export default async function HomePage() {
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );

  // ── Parallel fetch: all 4 data sources ──────────────────────────────────────
  const [
    { data: feasibilityData, error: feasibilityError },
    { data: regionsData, error: regionsError },
    frontier,
    clusters,
    osm,
  ] = await Promise.all([
    supabase
      .schema('indices')
      .from('grid_feasibility_current')
      .select('region_id, value, category, components'),
    supabase
      .schema('core')
      .from('regions')
      .select('id, name, admin_code, geometry'),
    fetchFrontierDCs(supabase),
    fetchClusterDCs(supabase),
    fetchOsmDCs(supabase),
  ]);

  // ── Error handling for required county data ──────────────────────────────────
  if (feasibilityError || !feasibilityData) {
    console.error('Feasibility fetch error:', feasibilityError);
    return (
      <main className="flex flex-col h-screen items-center justify-center text-red-600">
        Failed to load feasibility data: {feasibilityError?.message}
      </main>
    );
  }

  if (regionsError || !regionsData) {
    console.error('Regions fetch error:', regionsError);
    return (
      <main className="flex flex-col h-screen items-center justify-center text-red-600">
        Failed to load regions data: {regionsError?.message}
      </main>
    );
  }

  // ── JS join for county GeoJSON (§7.2 pattern) ───────────────────────────────
  const regionsMap = new Map(regionsData.map((r) => [r.id, r]));

  const features = feasibilityData
    .map((f) => {
      const region = regionsMap.get(f.region_id);
      if (!region?.geometry) return null;
      return {
        type: 'Feature' as const,
        geometry: region.geometry as MultiPolygon,
        properties: {
          name: region.name,
          admin_code: region.admin_code,
          value: f.value,
          category: f.category,
          headroom_mw: f.components?.headroom?.headroom_mw ?? 0,
          peak_demand_mw: f.components?.headroom?.peak_demand_mw ?? 0,
          q_realistic_mw: f.components?.queue?.q_realistic_mw ?? 0,
        },
      };
    })
    .filter((f) => f !== null) as Feature<MultiPolygon>[];

  const counties: FeatureCollection<MultiPolygon> = {
    type: 'FeatureCollection',
    features,
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <main className="flex flex-col h-screen">
      <Header />
      <AppShell
        counties={counties}
        datacenters={{ frontier, clusters, osm }}
      />
    </main>
  );
}
