// Several point objects at one spot (SPEC_DC_world_v0_2_0 4.4): Epoch has up to 3 sites in one point, and a click
// must show all of them. This lists the objects the map returned for the click; it does not count anything.

export interface SpotObject {
  source?: string;
  geometry: { type: string; coordinates?: unknown };
  properties?: Record<string, unknown> | null;
}

function xy(o: SpotObject): [number, number] | null {
  const c = o.geometry.coordinates;
  if (o.geometry.type !== 'Point' || !Array.isArray(c) || typeof c[0] !== 'number' || typeof c[1] !== 'number') return null;
  return [c[0], c[1]];
}

/** Two point objects at the same spot (tile coordinates are a grid, so objects at one spot have equal values). */
export function sameSpot(a: SpotObject, b: SpotObject): boolean {
  const p = xy(a);
  const q = xy(b);
  return Boolean(p && q && Math.abs(p[0] - q[0]) < 1e-7 && Math.abs(p[1] - q[1]) < 1e-7);
}

/**
 * The clicked object and every other object of the same layer at the same spot, one entry per record (the same
 * record can come once for each tile that holds it). The clicked object is first. Not a point: just the object.
 */
export function objectsAtSpot<T extends SpotObject>(objects: T[], top: T, keyField: string): T[] {
  if (!xy(top)) return [top];
  const seen = new Set<string>();
  const out: T[] = [];
  for (const x of [top, ...objects]) {
    if (x.source !== top.source || !sameSpot(x, top)) continue;
    const id = String(x.properties?.[keyField]);
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(x);
  }
  return out;
}
