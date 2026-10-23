// Country boxes for the search: from the ADM0 geometry at build time (never in the browser).
// A box follows the main body of a country and its near islands; far overseas parts (Hawaii, French Guiana,
// Svalbard) are left out, and a country that crosses the antimeridian gets east > 180 (Fiji: 177 .. 182).

const GAP = 10; // degrees: parts closer than this to the main body belong to the box

function polygonsOf(geom) {
  if (!geom) return [];
  if (geom.type === 'Polygon') return [geom.coordinates];
  if (geom.type === 'MultiPolygon') return geom.coordinates;
  if (geom.type === 'GeometryCollection') return geom.geometries.flatMap(polygonsOf);
  return [];
}

/** [w, s, e, n] of one polygon (outer ring); a ring that jumps over the antimeridian is read on the circle. */
function boxOfRing(ring) {
  let s = Infinity, n = -Infinity;
  const lons = [];
  for (const [x, y] of ring) {
    lons.push(x);
    if (y < s) s = y;
    if (y > n) n = y;
  }
  // unwrap: when consecutive points differ by more than 180 degrees, the ring crosses the antimeridian
  let w = lons[0], e = lons[0], prev = lons[0], off = 0;
  for (let i = 1; i < lons.length; i++) {
    const d = lons[i] - prev;
    if (d > 180) off -= 360;
    else if (d < -180) off += 360;
    prev = lons[i];
    const v = lons[i] + off;
    if (v < w) w = v;
    if (v > e) e = v;
  }
  return [w, s, e, n];
}

/** shift a box by multiples of 360 so that it is as near as possible to the centre longitude `c` */
function nearTo(b, c) {
  const mid = (b[0] + b[2]) / 2;
  const k = Math.round((c - mid) / 360);
  return [b[0] + 360 * k, b[1], b[2] + 360 * k, b[3]];
}

const gap = (a0, a1, b0, b1) => Math.max(0, Math.max(a0, b0) - Math.min(a1, b1));

/** The box of a feature: the biggest part, grown over every part within GAP degrees of it (repeatedly). */
export function featureBox(geom) {
  const parts = polygonsOf(geom).map((p) => boxOfRing(p[0])).filter((b) => Number.isFinite(b[0]));
  if (parts.length === 0) return null;
  const area = (b) => (b[2] - b[0]) * (b[3] - b[1]);
  parts.sort((a, b) => area(b) - area(a));
  let box = [...parts[0]];
  const rest = parts.slice(1);
  let grew = true;
  while (grew && rest.length) {
    grew = false;
    for (let i = rest.length - 1; i >= 0; i--) {
      const b = nearTo(rest[i], (box[0] + box[2]) / 2);
      if (gap(box[0], box[2], b[0], b[2]) <= GAP && gap(box[1], box[3], b[1], b[3]) <= GAP) {
        box = [Math.min(box[0], b[0]), Math.min(box[1], b[1]), Math.max(box[2], b[2]), Math.max(box[3], b[3])];
        rest.splice(i, 1);
        grew = true;
      }
    }
  }
  return box.map((v) => Math.round(v * 100) / 100);
}
