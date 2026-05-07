// app/components/AppShell.tsx
// Client Component wrapper for the main page interactive shell.
// Receives ALL data pre-fetched from the Server Component (page.tsx) as props.
// Manages: mobile sheet open/close state, layer state (URL-backed), layout.
//
// Suspense boundary is required here because AppShellInner calls useLayerState()
// which internally calls useSearchParams() — a Next.js 14 constraint.

'use client';

import { useState, Suspense } from 'react';
import type { FeatureCollection, MultiPolygon, Point } from 'geojson';

import MapComponent from './Map';
import LayerPanel from './LayerPanel';
import BottomSheet from './BottomSheet';
import Legend from './Legend';
import { useLayerState } from '@/lib/hooks/useLayerState';
import type { FrontierProps, ClusterProps, OsmProps } from '@/lib/queries/datacenters';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AppShellProps {
  counties: FeatureCollection<MultiPolygon>;
  datacenters: {
    frontier: FeatureCollection<Point, FrontierProps>;
    clusters: FeatureCollection<Point, ClusterProps>;
    osm: FeatureCollection<Point, OsmProps>;
  };
}

// ─── Inner component (calls useSearchParams via useLayerState) ────────────────

function AppShellInner({ counties, datacenters }: AppShellProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const layerState = useLayerState();

  return (
    <div className="flex flex-1 overflow-hidden">

      {/* ── Desktop sidebar (hidden on mobile) ─────────────────────────────── */}
      <aside className="hidden lg:flex flex-col w-[280px] flex-shrink-0 border-r border-gray-200 overflow-hidden">
        <LayerPanel layerState={layerState} />
      </aside>

      {/* ── Map area ───────────────────────────────────────────────────────── */}
      <div className="relative flex-1">
        <MapComponent
          counties={counties}
          datacenters={datacenters}
          layerState={layerState}
        />

        {/* Legend — bottom-left overlay inside map area */}
        <Legend />

        {/* Hamburger button — mobile only, floating top-left of map */}
        <button
          className="lg:hidden absolute top-3 left-3 z-20 bg-white rounded-lg shadow-md p-2 border border-gray-200 hover:bg-gray-50 transition-colors"
          onClick={() => setSheetOpen(true)}
          aria-label="Open layer panel"
        >
          {/* Hamburger icon (inline SVG — no icon lib dependency) */}
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <path
              d="M3 5h14M3 10h14M3 15h14"
              stroke="#374151"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      {/* ── Mobile bottom sheet ─────────────────────────────────────────────── */}
      {sheetOpen && (
        <BottomSheet onClose={() => setSheetOpen(false)}>
          <LayerPanel layerState={layerState} />
        </BottomSheet>
      )}
    </div>
  );
}

// ─── Public component (provides Suspense boundary) ────────────────────────────

export default function AppShell(props: AppShellProps) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-1 bg-gray-100 items-center justify-center">
          <span className="text-sm text-gray-400">Loading map…</span>
        </div>
      }
    >
      <AppShellInner {...props} />
    </Suspense>
  );
}
