// Units of the countries that have layers (territory.json, written at build time from units.csv of the boundaries
// dataset). Loaded once, on the first choice of a territory. No geometry: parents come from parent_id.

/** unit_id -> [level, name, parent_id] */
export type UnitTable = Record<string, [number, string, string]>;

export interface Territory {
  units: UnitTable;
}

let pending: Promise<Territory> | null = null;

export function loadTerritory(): Promise<Territory> {
  if (!pending) {
    pending = fetch('/territory.json')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Territory>;
      });
    pending.catch(() => {
      pending = null;
    });
  }
  return pending;
}

export function unitName(t: Territory | null, id: string): string {
  return t?.units[id]?.[1] ?? id;
}

/** unit ids from the country down to `id`, e.g. [USA, USA-1-08, USA-2-08001] */
export function chainOf(t: Territory | null, id: string): string[] {
  const out: string[] = [];
  let cur: string | undefined = id;
  for (let i = 0; cur && i < 6; i++) {
    out.unshift(cur);
    cur = t?.units[cur]?.[2] || undefined;
  }
  return out;
}

/** true when `id` is `ancestor` or lies inside it */
export function isWithin(t: Territory, id: string, ancestor: string): boolean {
  let cur: string | undefined = id;
  for (let i = 0; cur && i < 6; i++) {
    if (cur === ancestor) return true;
    cur = t.units[cur]?.[2] || undefined;
  }
  return false;
}

/** Levels (1, 2) the country has in the boundaries. */
export function levelsOfCountry(t: Territory | null, iso3: string): Set<number> | null {
  if (!t) return null;
  const s = new Set<number>([0]);
  const prefix = `${iso3}-`;
  for (const [id, u] of Object.entries(t.units)) if (id.startsWith(prefix)) s.add(u[0]);
  return s;
}
