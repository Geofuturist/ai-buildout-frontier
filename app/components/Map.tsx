'use client';

import 'maplibre-gl/dist/maplibre-gl.css';

import ReactMap, { Source, Layer, Popup } from 'react-map-gl/maplibre';
import { useState, useCallback } from 'react';
import type { FillLayer, LineLayer } from 'react-map-gl/maplibre';
import type { FeatureCollection } from 'geojson';
import type { MapLayerMouseEvent } from 'react-map-gl';

import { FEASIBILITY_COLORS, FEASIBILITY_LABELS, type FeasibilityCategory } from '@/lib/feasibility';

interface MapComponentProps {
  data: FeatureCollection;
}

const fillLayer: FillLayer = {
  id: 'counties-fill',
  type: 'fill',
  source: 'counties',
  paint: {
    'fill-color': [
      'match',
      ['get', 'category'],
      'high_feasibility',     FEASIBILITY_COLORS.high_feasibility,
      'moderate_feasibility', FEASIBILITY_COLORS.moderate_feasibility,
      'low_feasibility',      FEASIBILITY_COLORS.low_feasibility,
      'critical_constraint',  FEASIBILITY_COLORS.critical_constraint,
      'dc_hotspot',           FEASIBILITY_COLORS.dc_hotspot,
      '#cccccc',
    ],
    'fill-opacity': 0.6,
  },
};

const borderLayer: LineLayer = {
  id: 'counties-border',
  type: 'line',
  source: 'counties',
  paint: {
    'line-color': '#666',
    'line-width': 0.5,
  },
};

interface PopupInfo {
  longitude: number;
  latitude: number;
  name: string;
  value: number;
  category: FeasibilityCategory;
  headroom_mw: number;
  peak_demand_mw: number;
  q_realistic_mw: number;
}

export default function MapComponent({ data }: MapComponentProps) {
  const [popupInfo, setPopupInfo] = useState<PopupInfo | null>(null);

  const onClick = useCallback((event: MapLayerMouseEvent) => {
    const feature = event.features?.[0];
    if (!feature?.properties) return;

    const props = feature.properties;
    setPopupInfo({
      longitude: event.lngLat.lng,
      latitude: event.lngLat.lat,
      name: props.name ?? '',
      value: props.value ?? 0,
      category: props.category ?? 'low_feasibility',
      headroom_mw: props.headroom_mw ?? 0,
      peak_demand_mw: props.peak_demand_mw ?? 0,
      q_realistic_mw: props.q_realistic_mw ?? 0,
    });
  }, []);

  return (
    <ReactMap
      initialViewState={{
        longitude: -79.0,
        latitude: 37.5,
        zoom: 6.5,
      }}
      maxZoom={12}
      minZoom={5}
      style={{ width: '100%', height: '100%' }}
      mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
      interactiveLayerIds={['counties-fill']}
      onClick={onClick}
      cursor="default"
    >
      <Source id="counties" type="geojson" data={data}>
        <Layer {...fillLayer} />
        <Layer {...borderLayer} />
      </Source>

      {popupInfo && (
        <Popup
          longitude={popupInfo.longitude}
          latitude={popupInfo.latitude}
          anchor="bottom"
          onClose={() => setPopupInfo(null)}
          closeOnClick={false}
        >
          <div style={{ fontFamily: 'system-ui, sans-serif', minWidth: '200px', padding: '4px' }}>
            <p style={{ fontWeight: 600, fontSize: '14px', margin: '0 0 8px 0', borderBottom: '1px solid #eee', paddingBottom: '6px' }}>
              {popupInfo.name}
            </p>
            <table style={{ fontSize: '12px', borderCollapse: 'collapse', width: '100%' }}>
              <tbody>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Feasibility ratio</td>
                  <td style={{ fontWeight: 500 }}>{popupInfo.value.toFixed(2)}</td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Category</td>
                  <td style={{ fontWeight: 500, color: FEASIBILITY_COLORS[popupInfo.category] }}>
                    {(FEASIBILITY_LABELS[popupInfo.category] ?? popupInfo.category).split(' — ')[0]}
                  </td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Headroom</td>
                  <td style={{ fontWeight: 500 }}>{popupInfo.headroom_mw.toFixed(1)} MW</td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Peak demand</td>
                  <td style={{ fontWeight: 500 }}>{popupInfo.peak_demand_mw.toFixed(1)} MW</td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Queue (realistic)</td>
                  <td style={{ fontWeight: 500 }}>{popupInfo.q_realistic_mw.toFixed(1)} MW</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Popup>
      )}
    </ReactMap>
  );
}
