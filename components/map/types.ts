import type { AbfData } from '@/lib/data';

/** What the server page passes to the client map (no attribution, no warnings). */
export type MapData = Pick<AbfData, 'channel' | 'layers' | 'metas' | 'anchors' | 'datasets' | 'default_layer' | 'default_country' | 'level_zoom' | 'unit_words'>;

/** A unit chosen on the map: level 0 is the country itself (unit_id = its ISO3 code). */
export interface UnitRef {
  unit_id: string;
  name: string;
  level: number;
}

export type CardState =
  | { type: 'record'; layerId: string; props: Record<string, unknown> }
  | { type: 'layer'; layerId: string }
  | null;
