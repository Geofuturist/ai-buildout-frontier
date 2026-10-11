import type { AbfData } from '@/lib/data';

/** What the server page passes to the client map (no attribution, no warnings). */
export type MapData = Pick<AbfData, 'channel' | 'layers' | 'metas' | 'anchors' | 'datasets'>;

export type CardState =
  | { type: 'record'; layerId: string; props: Record<string, unknown> }
  | { type: 'layer'; layerId: string }
  | null;
