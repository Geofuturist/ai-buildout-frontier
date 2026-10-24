// The records of a place (SPEC_DC_world_v0_2_0 4.2): the places layer carries the number of records, the records
// themselves are rows of the published CSV of the layer of records, found by the place key. The file is fetched once
// (csvLoad) and indexed once; nothing is counted here: the list is what the file holds, and the number from the
// places layer is only compared with it.
import { groupRows, typedRow } from './csv';
import { loadCsv } from './csvLoad';
import type { LayerEntry, Meta } from './data';

/**
 * Key that ties a record to its place: a column of the CSV of both layers (contract of the layers with places, as
 * record_id and coord_precision are contract columns of every point layer).
 */
export const PLACE_KEY = 'place_ref';

/**
 * The layer that holds the records of the places of `place`: same dataset, a point layer with a CSV and the place
 * key, and not itself a layer of places (no count_field).
 */
export function placeRowsLayer(place: LayerEntry, layers: LayerEntry[], metas: Record<string, Meta>): LayerEntry | undefined {
  return layers.find((l) => {
    const m = metas[l.meta_id];
    return (
      l.dataset === place.dataset &&
      l.layer_id !== place.layer_id &&
      l.tiles.geometry_type === 'point' &&
      Boolean(l.files.csv) &&
      !m?.display?.count_field &&
      Boolean(m?.fields.some((f) => f.name === PLACE_KEY))
    );
  });
}

export type PlaceIndex = NonNullable<ReturnType<typeof groupRows>>;

const indexCache = new Map<string, Promise<PlaceIndex>>();

/** Fetches the CSV (once per page) and groups its rows by the place key (once per file). */
export function loadPlaceIndex(csvUrl: string): Promise<PlaceIndex> {
  let p = indexCache.get(csvUrl);
  if (!p) {
    p = loadCsv(csvUrl).then((text) => {
      const idx = groupRows(text, PLACE_KEY);
      if (!idx) throw new Error(`column ${PLACE_KEY} is missing`);
      return idx;
    });
    p.catch(() => indexCache.delete(csvUrl));
    indexCache.set(csvUrl, p);
  }
  return p;
}

/** Typed rows of one place, in file order. */
export function rowsOfPlace(idx: PlaceIndex, placeRef: string, meta: Meta): Record<string, unknown>[] {
  const types = Object.fromEntries(meta.fields.map((f) => [f.name, f.type]));
  return (idx.byKey.get(placeRef) ?? []).map((raw) => typedRow(idx.header, raw, types));
}
