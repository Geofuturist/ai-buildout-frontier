'use client';

import { useCallback, useRef, useState } from 'react';
import Link from 'next/link';
import MapCanvas from './MapCanvas';
import type { MapHandle } from './MapCanvas';
import LayerPanel from './LayerPanel';
import InfoCard from './InfoCard';
import CountryCard from './CountryCard';
import MapNav from './MapNav';
import { MODULE_BY_TYPE } from './modules';
import { countryNameFromIso3 } from '@/lib/iso3';
import { groupByCountry, pickCountryFill, unionBbox } from '@/lib/layers';
import { selectDataLayers } from './select';
import type { CardState, MapData } from './types';

export default function MapApp({ data }: { data: MapData }) {
  const mapRef = useRef<MapHandle>(null);
  // The fill layer that is on at start: content/site.json default_layer, otherwise the first fill layer
  const fills = selectDataLayers(data).filter((l) => MODULE_BY_TYPE[l.tiles.geometry_type].exclusive);
  const firstFill = fills.find((l) => l.layer_id === data.default_layer) ?? fills[0];
  const [activeId, setActiveId] = useState<string>(firstFill?.layer_id ?? 'none');
  const [overlays, setOverlays] = useState<Record<string, boolean>>({});
  const [card, setCard] = useState<CardState>(null);
  // Asks the layer panel to scroll a country's group into view (n makes a repeated click count)
  const [focus, setFocus] = useState<{ iso3: string; n: number } | null>(null);
  const [failed, setFailed] = useState<Set<string>>(new Set());

  const onFailed = useCallback((id: string) => setFailed((prev) => (prev.has(id) ? prev : new Set(prev).add(id))), []);

  const allLayers = selectDataLayers(data);
  const groups = groupByCountry(allLayers, data.metas, data.default_layer);

  // Package 1c: a click that hit no object of a switched-on layer but hit a country chooses the country
  const onCountry = (iso3: string) => {
    const group = groups.find((g) => g.iso3 === iso3);
    setCard({ type: 'country', iso3 });
    if (!group) return; // no layers: only the card; the layer on and the view stay as they are
    const panelOrder = group.domains.flatMap((d) => d.layers);
    const fills = panelOrder.filter((l) => MODULE_BY_TYPE[l.tiles.geometry_type].exclusive);
    const pick = pickCountryFill(fills, allLayers.find((l) => l.layer_id === activeId));
    if (pick) {
      setActiveId(pick.layer_id);
      const b = unionBbox([pick], data.metas);
      if (b) mapRef.current?.fitBounds(b);
    }
    setFocus((f) => ({ iso3, n: (f?.n ?? 0) + 1 }));
  };

  const selected = (() => {
    if (!card || card.type !== 'record') return null;
    const layer = data.layers.find((l) => l.layer_id === card.layerId);
    if (!layer) return null;
    const v = card.props[MODULE_BY_TYPE[layer.tiles.geometry_type].keyField];
    return v === undefined || v === null ? null : { layerId: card.layerId, key: String(v) };
  })();

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1">
        <MapCanvas
          ref={mapRef}
          data={data}
          activeId={activeId}
          overlays={overlays}
          selected={selected}
          onSelect={setCard}
          onCountry={onCountry}
          onFailed={onFailed}
        />
        <LayerPanel
          data={data}
          activeId={activeId}
          overlays={overlays}
          failed={failed}
          hidden={card !== null}
          focus={focus}
          onActive={(id) => { setActiveId(id); setCard(null); }}
          onOverlay={(id, on) => setOverlays((prev) => ({ ...prev, [id]: on }))}
          onInfo={(id) => setCard({ type: 'layer', layerId: id })}
          onZoom={(b) => mapRef.current?.fitBounds(b)}
          onWorld={() => mapRef.current?.fitWorld()}
        />
        <MapNav preview={data.channel === 'dev'} />
        <InfoCard data={data} card={card} onClose={() => setCard(null)} />
        {card?.type === 'country' && (() => {
          const group = groups.find((g) => g.iso3 === card.iso3);
          return (
            <CountryCard
              data={data}
              iso3={card.iso3}
              name={group?.name ?? countryNameFromIso3(card.iso3)}
              layers={group ? group.domains.flatMap((d) => d.layers) : []}
              activeId={activeId}
              overlays={overlays}
              onActive={setActiveId}
              onOverlay={(id, on) => setOverlays((prev) => ({ ...prev, [id]: on }))}
              onClose={() => setCard(null)}
            />
          );
        })()}
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
