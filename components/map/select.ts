import type { LayerEntry } from '@/lib/data';
import { MODULE_BY_TYPE } from './modules';
import type { MapData } from './types';

/** Layers the map can draw: published as data layers (kind 'layer') and handled by a module. */
export function selectDataLayers(data: Pick<MapData, 'layers' | 'metas'>): LayerEntry[] {
  return data.layers.filter((l) => {
    const meta = data.metas[l.meta_id];
    const mod = MODULE_BY_TYPE[l.tiles.geometry_type];
    return meta?.kind === 'layer' && Boolean(mod) && mod.accepts(l, meta);
  });
}

/** Boundary entries (kind 'boundaries'). */
export function selectBoundaryLayers(data: Pick<MapData, 'layers' | 'metas'>): LayerEntry[] {
  return data.layers.filter((l) => data.metas[l.meta_id]?.kind === 'boundaries');
}
