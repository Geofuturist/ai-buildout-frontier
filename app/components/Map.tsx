'use client';

import 'maplibre-gl/dist/maplibre-gl.css';

import ReactMap, { Source, Layer, Popup, type MapRef } from 'react-map-gl/maplibre';
import { useState, useCallback, useRef, useMemo } from 'react';
import type {
  FillLayerSpecification,
  LineLayerSpecification,
  FilterSpecification,
  GeoJSONSource,
} from 'maplibre-gl';
import type { FeatureCollection, MultiPolygon, Point } from 'geojson';
import type { MapLayerMouseEvent } from 'react-map-gl/maplibre';

import { FEASIBILITY_COLORS, FEASIBILITY_LABELS, type FeasibilityCategory } from '@/lib/feasibility';
import { DC_STATUS_COLORS, type DCStatus, type FrontierProps, type ClusterProps, type OsmProps } from '@/lib/queries/datacenters';
import type { LayerState } from '@/lib/hooks/useLayerState';
import { DCPopup } from './DCPopup';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildStatusFilter(showPlanned: boolean, showDecom: boolean): FilterSpecification {
  const allowed: string[] = ['operational', 'under_construction', 'unknown'];
  if (showPlanned) allowed.push('planned', 'announced');
  if (showDecom) allowed.push('decommissioned');
  return ['in', ['get', 'status'], ['literal', allowed]] as unknown as FilterSpecification;
}

// ─── Static layer specs ───────────────────────────────────────────────────────

const countiesFillLayer: FillLayerSpecification = {
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

const countiesBorderLayer: LineLayerSpecification = {
  id: 'counties-border',
  type: 'line',
  source: 'counties',
  paint: {
    'line-color': '#666',
    'line-width': 0.5,
  },
};

// ─── Popup state types ────────────────────────────────────────────────────────

interface CountyPopupInfo {
  type: 'county';
  longitude: number;
  latitude: number;
  name: string;
  value: number;
  category: FeasibilityCategory;
  headroom_mw: number;
  peak_demand_mw: number;
  q_realistic_mw: number;
}

interface DCPopupInfo {
  type: 'dc';
  layer: 'frontier-circles' | 'clusters-points' | 'osm-points';
  coordinates: [number, number];
  properties: Record<string, unknown>;
}

type ActivePopup = CountyPopupInfo | DCPopupInfo | null;

// ─── Props ────────────────────────────────────────────────────────────────────

interface MapComponentProps {
  counties: FeatureCollection<MultiPolygon>;
  datacenters: {
    frontier: FeatureCollection<Point, FrontierProps>;
    clusters: FeatureCollection<Point, ClusterProps>;
    osm: FeatureCollection<Point, OsmProps>;
  };
  layerState: LayerState;
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function MapComponent({ counties, datacenters, layerState }: MapComponentProps) {
  const mapRef = useRef<MapRef>(null);
  const [activePopup, setActivePopup] = useState<ActivePopup>(null);
  const [cursor, setCursor] = useState<string>('auto');

  const {
    feasibilityEnabled,
    frontierEnabled,
    clustersEnabled,
    osmEnabled,
    frontierShowPlanned,
    frontierShowDecom,
    clustersShowPlanned,
    clustersShowDecom,
  } = layerState;

  const frontierFilter = useMemo(
    () => buildStatusFilter(frontierShowPlanned, frontierShowDecom),
    [frontierShowPlanned, frontierShowDecom],
  );

  const clustersFilter = useMemo(
    () => buildStatusFilter(clustersShowPlanned, clustersShowDecom),
    [clustersShowPlanned, clustersShowDecom],
  );

  const handleMapClick = useCallback(
    (event: MapLayerMouseEvent) => {
      if (!event.features || event.features.length === 0) {
        setActivePopup(null);
        return;
      }

      const feature = event.features[0];
      if (!feature) return;

      const layerId = feature.layer.id;

      // Cluster bubble → zoom in
      if (layerId === 'clusters-cluster-bubbles' || layerId === 'osm-cluster-bubbles') {
        const clusterId = feature.properties?.cluster_id as number | undefined;
        if (clusterId == null) return;
        const sourceId = layerId.startsWith('clusters') ? 'clusters-dc' : 'osm-dc';
        const map = mapRef.current?.getMap();
        const source = map?.getSource(sourceId) as GeoJSONSource | undefined;
        if (source && 'getClusterExpansionZoom' in source) {
          // maplibre-gl v4: getClusterExpansionZoom returns a Promise<number>
          (source.getClusterExpansionZoom(clusterId) as Promise<number>)
            .then((zoom: number) => {
              if (feature.geometry.type !== 'Point') return;
              const [lng, lat] = feature.geometry.coordinates;
              mapRef.current?.easeTo({ center: [lng as number, lat as number], zoom });
            })
            .catch(() => {/* cluster expansion zoom failed — ignore */});
        }
        return;
      }

      // DC individual point → popup
      if (
        layerId === 'frontier-circles' ||
        layerId === 'clusters-points' ||
        layerId === 'osm-points'
      ) {
        if (feature.geometry.type !== 'Point') return;
        const [lng, lat] = feature.geometry.coordinates;
        setActivePopup({
          type: 'dc',
          layer: layerId as DCPopupInfo['layer'],
          coordinates: [lng as number, lat as number],
          properties: (feature.properties ?? {}) as Record<string, unknown>,
        });
        return;
      }

      // County → existing popup (no regression)
      if (layerId === 'counties-fill') {
        const props = feature.properties;
        if (!props) return;
        setActivePopup({
          type: 'county',
          longitude: event.lngLat.lng,
          latitude: event.lngLat.lat,
          name: String(props.name ?? ''),
          value: Number(props.value ?? 0),
          category: (props.category ?? 'low_feasibility') as FeasibilityCategory,
          headroom_mw: Number(props.headroom_mw ?? 0),
          peak_demand_mw: Number(props.peak_demand_mw ?? 0),
          q_realistic_mw: Number(props.q_realistic_mw ?? 0),
        });
      }
    },
    [],
  );

  const onMouseEnter = useCallback(() => setCursor('pointer'), []);
  const onMouseLeave = useCallback(() => setCursor('auto'), []);

  return (
    <ReactMap
      ref={mapRef}
      initialViewState={{
        longitude: -79.0,
        latitude: 37.5,
        zoom: 6.5,
      }}
      maxZoom={14}
      minZoom={4}
      style={{ width: '100%', height: '100%' }}
      mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
      interactiveLayerIds={[
        'counties-fill',
        'frontier-circles',
        'clusters-points',
        'clusters-cluster-bubbles',
        'osm-points',
        'osm-cluster-bubbles',
      ]}
      onClick={handleMapClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      cursor={cursor}
    >
      {/* 1. County feasibility choropleth (bottom) */}
      <Source id="counties" type="geojson" data={counties}>
        <Layer
          {...countiesFillLayer}
          layout={{ visibility: feasibilityEnabled ? 'visible' : 'none' }}
        />
        <Layer
          {...countiesBorderLayer}
          layout={{ visibility: feasibilityEnabled ? 'visible' : 'none' }}
        />
      </Source>

      {/* 2. OSM datacenters (lowest DC layer) */}
      <Source
        id="osm-dc"
        type="geojson"
        data={datacenters.osm}
        cluster={true}
        clusterRadius={40}
        clusterMaxZoom={7}
      >
        <Layer
          id="osm-cluster-bubbles"
          type="circle"
          source="osm-dc"
          filter={['has', 'point_count']}
          layout={{ visibility: osmEnabled ? 'visible' : 'none' }}
          paint={{
            'circle-radius': ['step', ['get', 'point_count'], 12, 100, 16, 500, 20],
            'circle-color': '#475569',
            'circle-opacity': 0.55,
            'circle-stroke-width': 1,
            'circle-stroke-color': '#ffffff',
          }}
        />
        <Layer
          id="osm-cluster-counts"
          type="symbol"
          source="osm-dc"
          filter={['has', 'point_count']}
          layout={{
            visibility: osmEnabled ? 'visible' : 'none',
            'text-field': '{point_count_abbreviated}',
            'text-size': 11,
            'text-allow-overlap': true,
          }}
          paint={{ 'text-color': '#ffffff' }}
        />
        <Layer
          id="osm-points"
          type="circle"
          source="osm-dc"
          filter={['!', ['has', 'point_count']]}
          layout={{ visibility: osmEnabled ? 'visible' : 'none' }}
          paint={{
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 2, 8, 3, 12, 5],
            'circle-color': '#64748b',
            'circle-opacity': 0.7,
            'circle-stroke-width': 0.5,
            'circle-stroke-color': '#ffffff',
          }}
        />
      </Source>

      {/* 3. GPU Clusters (Epoch) */}
      <Source
        id="clusters-dc"
        type="geojson"
        data={datacenters.clusters}
        cluster={true}
        clusterRadius={50}
        clusterMaxZoom={6}
      >
        <Layer
          id="clusters-cluster-bubbles"
          type="circle"
          source="clusters-dc"
          filter={['has', 'point_count']}
          layout={{ visibility: clustersEnabled ? 'visible' : 'none' }}
          paint={{
            'circle-radius': ['step', ['get', 'point_count'], 14, 50, 18, 200, 24],
            'circle-color': '#1e40af',
            'circle-opacity': 0.65,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff',
          }}
        />
        <Layer
          id="clusters-cluster-counts"
          type="symbol"
          source="clusters-dc"
          filter={['has', 'point_count']}
          layout={{
            visibility: clustersEnabled ? 'visible' : 'none',
            'text-field': '{point_count_abbreviated}',
            'text-size': 12,
            'text-allow-overlap': true,
          }}
          paint={{ 'text-color': '#ffffff' }}
        />
        <Layer
          id="clusters-points"
          type="circle"
          source="clusters-dc"
          filter={(['all', ['!', ['has', 'point_count']], clustersFilter] as unknown) as FilterSpecification}
          layout={{ visibility: clustersEnabled ? 'visible' : 'none' }}
          paint={{
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 5, 8, 7, 12, 10],
            'circle-color': [
              'match', ['get', 'status'],
              'operational',        DC_STATUS_COLORS.operational,
              'under_construction', DC_STATUS_COLORS.under_construction,
              'planned',            DC_STATUS_COLORS.planned,
              'announced',          DC_STATUS_COLORS.announced,
              'decommissioned',     DC_STATUS_COLORS.decommissioned,
              DC_STATUS_COLORS.unknown,
            ],
            'circle-stroke-width': 1.5,
            'circle-stroke-color': '#ffffff',
            'circle-opacity': [
              'match', ['get', 'geocoding_precision'],
              'street_level',     1.0,
              'city',             0.85,
              'region',           0.6,
              'country_centroid', 0.4,
              0.85,
            ],
          }}
        />
      </Source>

      {/* 4. Frontier AI datacenters (top — no clustering) */}
      <Source id="frontier-dc" type="geojson" data={datacenters.frontier}>
        <Layer
          id="frontier-circles"
          type="circle"
          source="frontier-dc"
          filter={frontierFilter}
          layout={{ visibility: frontierEnabled ? 'visible' : 'none' }}
          paint={{
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 8, 6, 12, 10, 18],
            'circle-color': [
              'match', ['get', 'status'],
              'operational',        DC_STATUS_COLORS.operational,
              'under_construction', DC_STATUS_COLORS.under_construction,
              'planned',            DC_STATUS_COLORS.planned,
              'announced',          DC_STATUS_COLORS.announced,
              'decommissioned',     DC_STATUS_COLORS.decommissioned,
              DC_STATUS_COLORS.unknown,
            ],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff',
            'circle-opacity': 0.9,
          }}
        />
      </Source>

      {/* County popup */}
      {activePopup?.type === 'county' && (
        <Popup
          longitude={activePopup.longitude}
          latitude={activePopup.latitude}
          anchor="bottom"
          onClose={() => setActivePopup(null)}
          closeOnClick={false}
        >
          <div style={{ fontFamily: 'system-ui, sans-serif', minWidth: '200px', padding: '4px' }}>
            <p style={{ fontWeight: 600, fontSize: '14px', margin: '0 0 8px 0', borderBottom: '1px solid #eee', paddingBottom: '6px' }}>
              {activePopup.name}
            </p>
            <table style={{ fontSize: '12px', borderCollapse: 'collapse', width: '100%' }}>
              <tbody>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Feasibility ratio</td>
                  <td style={{ fontWeight: 500 }}>{activePopup.value.toFixed(2)}</td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Category</td>
                  <td style={{ fontWeight: 500, color: FEASIBILITY_COLORS[activePopup.category] }}>
                    {(FEASIBILITY_LABELS[activePopup.category] ?? activePopup.category).split(' — ')[0]}
                  </td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Headroom</td>
                  <td style={{ fontWeight: 500 }}>{activePopup.headroom_mw.toFixed(1)} MW</td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Peak demand</td>
                  <td style={{ fontWeight: 500 }}>{activePopup.peak_demand_mw.toFixed(1)} MW</td>
                </tr>
                <tr>
                  <td style={{ color: '#666', padding: '2px 8px 2px 0' }}>Queue (realistic)</td>
                  <td style={{ fontWeight: 500 }}>{activePopup.q_realistic_mw.toFixed(1)} MW</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Popup>
      )}

      {/* DC popup */}
      {activePopup?.type === 'dc' && (
        <DCPopup
          layer={activePopup.layer}
          coordinates={activePopup.coordinates}
          properties={activePopup.properties}
          onClose={() => setActivePopup(null)}
        />
      )}
    </ReactMap>
  );
}
