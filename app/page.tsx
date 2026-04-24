import { createClient } from '@supabase/supabase-js';
import type { FeatureCollection, Feature, MultiPolygon } from 'geojson';
import MapComponent from './components/Map';
import Header from './components/Header';
import Legend from './components/Legend';

// Server Component — data fetched at request time on the server
export default async function HomePage() {
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!
  );

  // Query 1: feasibility data from indices schema
  const { data: feasibilityData, error: feasibilityError } = await supabase
    .schema('indices')
    .from('grid_feasibility_current')
    .select('region_id, value, category, components');

  if (feasibilityError || !feasibilityData) {
    console.error('Feasibility fetch error:', feasibilityError);
    return (
      <main className="flex flex-col h-screen items-center justify-center text-red-600">
        Failed to load feasibility data: {feasibilityError?.message}
      </main>
    );
  }

  // Query 2: region geometries from core schema
  const { data: regionsData, error: regionsError } = await supabase
    .schema('core')
    .from('regions')
    .select('id, name, admin_code, geometry');

  if (regionsError || !regionsData) {
    console.error('Regions fetch error:', regionsError);
    return (
      <main className="flex flex-col h-screen items-center justify-center text-red-600">
        Failed to load regions data: {regionsError?.message}
      </main>
    );
  }

  // Join in JavaScript by region_id
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

  const geojsonData: FeatureCollection = {
    type: 'FeatureCollection',
    features,
  };

  return (
    <main className="flex flex-col h-screen">
      <Header />
      <div className="relative flex-1">
        <MapComponent data={geojsonData} />
        <Legend />
      </div>
    </main>
  );
}
