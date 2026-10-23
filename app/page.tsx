import MapLoader from '@/components/map/MapLoader';
import { getData } from '@/lib/data';

export default function HomePage() {
  const d = getData();
  // Only what the map needs goes to the browser.
  const data = { channel: d.channel, layers: d.layers, metas: d.metas, anchors: d.anchors, datasets: d.datasets,
    default_layer: d.default_layer,
    default_country: d.default_country,
    level_zoom: d.level_zoom,
    unit_words: d.unit_words,
    countries: d.countries,
  };
  return (
    <div className="flex h-[100dvh] flex-col">
      <main className="flex min-h-0 flex-1 flex-col">
        <h1 className="sr-only">AI Buildout Frontier: map of open data layers on the physical side of AI</h1>
        <MapLoader data={data} />
      </main>
    </div>
  );
}
