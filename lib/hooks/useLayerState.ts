// lib/hooks/useLayerState.ts
// Reads layer toggle state from URL search params and provides an update function.
// IMPORTANT: Components calling this hook must be rendered inside a <Suspense>
// boundary because useSearchParams() opts the component into client-side
// rendering in Next.js 14 App Router.

'use client';

import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useCallback } from 'react';

// ─── Types ────────────────────────────────────────────────────────────────────

/** The settable boolean state fields (no 'update' function). */
export type LayerStateValues = {
  feasibilityEnabled: boolean;
  frontierEnabled: boolean;
  clustersEnabled: boolean;
  osmEnabled: boolean;
  frontierShowPlanned: boolean;
  frontierShowDecom: boolean;
  clustersShowPlanned: boolean;
  clustersShowDecom: boolean;
};

/** Full state object including the update function — passed as a single prop. */
export type LayerState = LayerStateValues & {
  update: (updates: Partial<LayerStateValues>) => void;
};

// ─── URL schema (SPEC §11.1) ──────────────────────────────────────────────────
//
// ?layers=feasibility,frontier   — which layers are ON (csv)
// ?fp=1                          — frontier show planned (default: 1)
// ?fd=0                          — frontier show decommissioned (default: 0)
// ?cp=1                          — clusters show planned (default: 1)
// ?cd=0                          — clusters show decommissioned (default: 0)
//
// Params with default values are OMITTED from URL to keep links clean.

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useLayerState(): LayerState {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  // Parse current state from URL (with defaults matching SPEC §4.2 / §4.4)
  const layersParam = searchParams.get('layers') ?? 'feasibility,frontier';
  const enabledLayers = new Set(layersParam.split(',').filter(Boolean));

  const values: LayerStateValues = {
    feasibilityEnabled:   enabledLayers.has('feasibility'),
    frontierEnabled:      enabledLayers.has('frontier'),
    clustersEnabled:      enabledLayers.has('clusters'),
    osmEnabled:           enabledLayers.has('osm'),
    frontierShowPlanned:  (searchParams.get('fp') ?? '1') === '1',
    frontierShowDecom:    (searchParams.get('fd') ?? '0') === '1',
    clustersShowPlanned:  (searchParams.get('cp') ?? '1') === '1',
    clustersShowDecom:    (searchParams.get('cd') ?? '0') === '1',
  };

  const update = useCallback(
    (updates: Partial<LayerStateValues>) => {
      const next: LayerStateValues = { ...values, ...updates };
      const params = new URLSearchParams();

      // Build layers csv — omit param entirely if all are OFF
      const enabled: string[] = [];
      if (next.feasibilityEnabled) enabled.push('feasibility');
      if (next.frontierEnabled)    enabled.push('frontier');
      if (next.clustersEnabled)    enabled.push('clusters');
      if (next.osmEnabled)         enabled.push('osm');
      if (enabled.length > 0) params.set('layers', enabled.join(','));

      // Only set sub-toggle params when they differ from default (keeps URLs cleaner)
      if (!next.frontierShowPlanned)  params.set('fp', '0');
      if (next.frontierShowDecom)     params.set('fd', '1');
      if (!next.clustersShowPlanned)  params.set('cp', '0');
      if (next.clustersShowDecom)     params.set('cd', '1');

      const qs = params.toString();
      router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      values.feasibilityEnabled,
      values.frontierEnabled,
      values.clustersEnabled,
      values.osmEnabled,
      values.frontierShowPlanned,
      values.frontierShowDecom,
      values.clustersShowPlanned,
      values.clustersShowDecom,
      pathname,
      router,
    ],
  );

  return { ...values, update };
}
