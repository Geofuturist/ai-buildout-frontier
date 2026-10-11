'use client';

import dynamic from 'next/dynamic';
import type { MapData } from './types';

// The map needs the browser (WebGL), so it is never rendered on the server.
const MapApp = dynamic(() => import('./MapApp'), {
  ssr: false,
  loading: () => (
    <div className="flex flex-1 items-center justify-center text-sm text-ink2" role="status">
      Loading map…
    </div>
  ),
});

export default function MapLoader({ data }: { data: MapData }) {
  return <MapApp data={data} />;
}
