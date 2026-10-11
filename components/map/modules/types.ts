import type { ReactNode } from 'react';
import type { FieldDef, LayerEntry, Meta } from '@/lib/data';

export type GeometryType = 'polygon' | 'line' | 'point';

export interface ModuleCtx {
  metas: Record<string, Meta>;
  /** layer_ids that are switched on */
  visible: Set<string>;
  /** the record shown in the card, if it belongs to a layer of this module */
  selected: { layerId: string; key: string } | null;
  /** id of the first label layer of the basemap: our layers go under it */
  before: string;
}

/** One drawing module per geometry type (SPEC_WEB 0.3). Chosen by tiles.geometry_type. */
export interface GeometryModule {
  type: GeometryType;
  /** true: one layer at a time (radio list). false: overlays (checkboxes) */
  exclusive: boolean;
  /** identity column of a record in tiles and CSV (SPEC_META): unit_id or record_id */
  keyField: string;
  /** the record card offers "Download this ...: CSV" */
  recordDownload: boolean;
  accepts: (layer: LayerEntry, meta: Meta | undefined) => boolean;
  renderLayers: (layers: LayerEntry[], ctx: ModuleCtx) => ReactNode;
  /** ids of the invisible hit layers: only these are clickable */
  hitLayerIds: (layerId: string) => string[];
  /** legend block for the layers of this type that are on */
  Legend: (props: { layers: LayerEntry[]; metas: Record<string, Meta> }) => ReactNode;
  /** optional: custom text for a value in the record card (return null for the default) */
  formatValue?: (field: FieldDef, value: unknown, meta: Meta) => string | null;
}
