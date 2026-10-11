'use client';

import { useCallback, useRef, useState } from 'react';
import Link from 'next/link';
import MapCanvas from './MapCanvas';
import type { MapHandle } from './MapCanvas';
import LayerPanel from './LayerPanel';
import InfoCard from './InfoCard';
import type { CardState, MapData } from './types';

export default function MapApp({ data }: { data: MapData }) {
  const mapRef = useRef<MapHandle>(null);
  const firstPoly = data.layers.find(
    (l) => l.dataset === 'abf-layers' && l.tiles.geometry_type === 'polygon' && data.metas[l.meta_id]?.display?.value_field,
  );
  const [activeId, setActiveId] = useState<string>(firstPoly?.layer_id ?? 'none');
  const [linesOn, setLinesOn] = useState<Record<string, boolean>>({});
  const [card, setCard] = useState<CardState>(null);
  const [failed, setFailed] = useState<Set<string>>(new Set());

  const onFailed = useCallback((id: string) => setFailed((prev) => (prev.has(id) ? prev : new Set(prev).add(id))), []);

  const selectedUnit = card && card.type === 'record' && typeof card.props.unit_id === 'string' ? card.props.unit_id : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1">
        <MapCanvas
          ref={mapRef}
          data={data}
          activeId={activeId}
          linesOn={linesOn}
          selectedUnit={selectedUnit}
          onSelect={setCard}
          onFailed={onFailed}
        />
        <LayerPanel
          data={data}
          activeId={activeId}
          linesOn={linesOn}
          failed={failed}
          hidden={card !== null}
          onActive={(id) => { setActiveId(id); setCard(null); }}
          onLines={(id, on) => setLinesOn((prev) => ({ ...prev, [id]: on }))}
          onInfo={(id) => setCard({ type: 'layer', layerId: id })}
          onUS={() => mapRef.current?.fitUS()}
          onWorld={() => mapRef.current?.fitWorld()}
        />
        <InfoCard data={data} card={card} onClose={() => setCard(null)} />
      </div>

      {/* Always visible, including on a phone (SPEC_WEB 4.6) */}
      <div className="shrink-0 border-t border-line bg-surface px-3 py-1.5 text-[11px] leading-snug text-ink2">
        © <a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a> ©{' '}
        <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>
        {' · '}
        <Link href="/attribution/" className="font-semibold">Sources and licenses</Link>
      </div>
    </div>
  );
}
