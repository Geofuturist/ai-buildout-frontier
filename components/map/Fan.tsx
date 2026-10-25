'use client';

// The fan of one place (SPEC_DC_world_v0_2_0 9 p. 3). The records of a place have no coordinates of their own, so
// they are laid out in screen pixels around the badge, at the moment of the click: not geographic positions, nothing
// here is stored, put in an address or downloaded. A line runs from each record to the point of the place, which stays
// where it is. The fan closes when the map moves or zooms, or when something else is clicked (MapApp).
// Colour by operator type (the groups file) and size by size class come from the rows of the published CSV.
import { useEffect, useMemo, useState } from 'react';
import type { LayerEntry } from '@/lib/data';
import { PLACE_KEY, loadPlaceIndex, loadTypeGroups, GROUPS_FILE, placeRowsLayer, rowsOfGroup, rowsOfPlace } from '@/lib/placeRows';
import { RING_EXTRA, SIZE_RADII, UNKNOWN_RADIUS, filterColumn, isTyped, typeColor, TYPE_GREY } from '@/lib/pointSize';
import { COLORS } from '@/lib/style';
import { str } from './DcPointRows';
import type { FanSpot, MapData } from './types';

type Row = Record<string, unknown>;

const MARK = 12; // px of the clickable mark around a record
const FIRST_RING = 52;
const RING_STEP = 30;

/** Positions on rings around the centre: as many marks on a ring as fit with a gap, the rest on the next ring. */
export function ringLayout(n: number): { dx: number; dy: number }[] {
  const out: { dx: number; dy: number }[] = [];
  let left = n;
  let r = FIRST_RING;
  let ring = 0;
  while (left > 0) {
    const cap = Math.max(6, Math.floor((2 * Math.PI * r) / (MARK * 2 + 6)));
    const k = Math.min(left, cap);
    const turn = ring % 2 ? Math.PI / k : 0;
    for (let i = 0; i < k; i++) {
      const a = -Math.PI / 2 + turn + (2 * Math.PI * i) / k;
      out.push({ dx: r * Math.cos(a), dy: r * Math.sin(a) });
    }
    left -= k;
    r += RING_STEP;
    ring++;
  }
  return out;
}

export default function Fan({ data, spot, typeFilter, onOpen }: { data: MapData; spot: FanSpot; typeFilter: string | null; onOpen: (layer: LayerEntry, row: Row) => void }) {
  const placeLayer = data.layers.find((l) => l.layer_id === spot.layerId);
  const meta = placeLayer ? data.metas[placeLayer.meta_id] : undefined;
  const d = meta?.display;
  const rowsLayer = placeLayer ? placeRowsLayer(placeLayer, data.layers, data.metas) : undefined;
  const rowsMeta = rowsLayer ? data.metas[rowsLayer.meta_id] : undefined;
  const csvUrl = rowsLayer?.files.csv?.url;
  const groupsUrl = placeLayer?.extra_files.find((f) => f.path === GROUPS_FILE)?.url;
  const ref = str(spot.props[PLACE_KEY]);
  const column = d ? filterColumn(d, typeFilter) : null;
  const [rows, setRows] = useState<Row[] | null>(null);
  const [groups, setGroups] = useState<Map<string, string> | null>(null);

  useEffect(() => {
    let live = true;
    setRows(null);
    if (!csvUrl || !rowsMeta || !ref) return;
    Promise.all([loadPlaceIndex(csvUrl), groupsUrl ? loadTypeGroups(groupsUrl) : Promise.resolve(null)])
      .then(([idx, g]) => {
        if (!live) return;
        let all = rowsOfPlace(idx, ref, rowsMeta);
        if (column && typeFilter && g) all = rowsOfGroup(all, g, typeFilter);
        setGroups(g);
        setRows(all);
      })
      .catch((e) => console.error(`fan ${ref}: could not read the records (${e instanceof Error ? e.message : String(e)})`));
    return () => {
      live = false;
    };
  }, [csvUrl, rowsMeta, groupsUrl, ref, column, typeFilter]);

  const spots = useMemo(() => (rows ? ringLayout(rows.length) : []), [rows]);
  if (!placeLayer || !rowsLayer || !rows || rows.length < 2 || !d) return null;

  const classes = d.size_classes ?? [];
  const colorClasses = isTyped(d) ? d.color_classes : [];
  const markOf = (row: Row) => {
    const group = groups?.get(str(row.operator_type)) ?? '';
    const i = colorClasses.indexOf(group);
    const col = i >= 0 ? typeColor(i) : TYPE_GREY;
    const ci = classes.indexOf(str(row.power_class));
    const known = ci >= 0 && str(row.power_status) !== 'not_found';
    return { col, r: known ? SIZE_RADII[Math.min(ci, SIZE_RADII.length - 1)] : UNKNOWN_RADIUS };
  };
  const reach = Math.max(0, ...spots.map((q) => Math.hypot(q.dx, q.dy))) + MARK + 14;

  return (
    <div className="pointer-events-none absolute inset-0 z-10" aria-label="Fan of the records of this place">
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        {spots.map((s, i) => (
          <line key={i} x1={spot.x} y1={spot.y} x2={spot.x + s.dx} y2={spot.y + s.dy} stroke="#3f4752" strokeOpacity="0.55" strokeWidth="1" />
        ))}
      </svg>
      {rows.map((row, i) => {
        const s = spots[i];
        if (!s) return null;
        const m = markOf(row);
        const name = str(row.name) || str(row.record_id);
        return (
          <button
            key={str(row.record_id) || i}
            type="button"
            title={name}
            aria-label={name}
            className="pointer-events-auto absolute flex items-center justify-center rounded-full"
            style={{ left: spot.x + s.dx - 14, top: spot.y + s.dy - 14, width: 28, height: 28 }}
            onClick={(e) => {
              e.stopPropagation();
              onOpen(rowsLayer, row);
            }}
          >
            <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden>
              <circle cx="14" cy="14" r={m.r + RING_EXTRA} fill={COLORS.surface} fillOpacity="0.9" />
              <circle cx="14" cy="14" r={m.r} fill={m.col.fill} fillOpacity="0.7" stroke={m.col.stroke} strokeWidth="1.2" />
            </svg>
          </button>
        );
      })}
      {d.fan_note && (
        <p
          className="pointer-events-none absolute w-60 -translate-x-1/2 rounded-md border border-line bg-surface/95 px-2 py-1 text-center text-xs text-ink2 shadow"
          style={{ left: spot.x, top: spot.y + reach }}
        >
          {d.fan_note}
        </p>
      )}
    </div>
  );
}
