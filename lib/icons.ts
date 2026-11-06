// Point icons: shape (by domain) x kind of status x colour (by type). SPEC_WEB_territory r11 par. 18.
// An icon is drawn on demand: the map asks for an image by id ("abf:circle:hatch:#F2C500"), the id says everything, so
// there is no list of icons to keep. Nothing here knows a layer: shapes, kinds and their words come from the meta.

export type Shape = 'circle' | 'square';
/** fill = works; pale = built, not working; hatch = under construction; outline = announced; q = shelved; x = cancelled */
export type Kind = 'fill' | 'pale' | 'hatch' | 'outline' | 'q' | 'x';

export const KINDS: Kind[] = ['fill', 'pale', 'hatch', 'outline', 'q', 'x'];
export const SHAPES: Shape[] = ['circle', 'square'];
/** kinds that need room to be read: at the smallest class they take the size of the next class */
export const FINE_KINDS: Kind[] = ['hatch', 'q', 'x'];

/** canvas of an icon (device px), pixel ratio, and the diameter of the drawn shape in css px at icon-size 1 */
export const ICON_PX = 64;
export const ICON_RATIO = 2;
const INSET = 3;
export const DRAWN = (ICON_PX / 2 - INSET) * 2 / ICON_RATIO;

export const ICON_PREFIX = 'abf:';

export function iconId(shape: Shape, kind: Kind, color: string): string {
  return `${ICON_PREFIX}${shape}:${kind}:${color}`;
}

export function parseIconId(id: string): { shape: Shape; kind: Kind; color: string } | null {
  if (!id.startsWith(ICON_PREFIX)) return null;
  const [shape, kind, color] = id.slice(ICON_PREFIX.length).split(':');
  if (!SHAPES.includes(shape as Shape) || !KINDS.includes(kind as Kind) || !/^#[0-9a-fA-F]{6}$/.test(color ?? '')) return null;
  return { shape: shape as Shape, kind: kind as Kind, color };
}

/** Draws one icon on a canvas of ICON_PX x ICON_PX (device px). */
export function drawIcon(ctx: CanvasRenderingContext2D, shape: Shape, kind: Kind, color: string): void {
  const c = ICON_PX / 2;
  const r = c - INSET;
  const path = () => {
    ctx.beginPath();
    if (shape === 'circle') ctx.arc(c, c, r, 0, Math.PI * 2);
    else ctx.rect(c - r, c - r, 2 * r, 2 * r);
  };
  ctx.clearRect(0, 0, ICON_PX, ICON_PX);
  ctx.lineJoin = 'miter';
  // light halo around everything, so that the icon stays readable over any basemap
  path();
  ctx.lineWidth = kind === 'fill' ? 5 : 9;
  ctx.strokeStyle = 'rgba(252,252,251,0.9)';
  ctx.stroke();
  if (kind === 'fill') {
    path();
    ctx.fillStyle = color;
    ctx.fill();
    return;
  }
  if (kind === 'pale') {
    path();
    ctx.fillStyle = 'rgba(252,252,251,0.75)';
    ctx.fill();
    ctx.globalAlpha = 0.38;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.globalAlpha = 0.85;
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.stroke();
    ctx.globalAlpha = 1;
    return;
  }
  // outline kinds: a light inside, the outline in the colour of the type
  path();
  ctx.fillStyle = 'rgba(252,252,251,0.6)';
  ctx.fill();
  if (kind === 'hatch') {
    ctx.save();
    path();
    ctx.clip();
    ctx.strokeStyle = color;
    ctx.lineWidth = 4;
    for (let k = -ICON_PX; k < ICON_PX * 2; k += 10) {
      ctx.beginPath();
      ctx.moveTo(k, ICON_PX);
      ctx.lineTo(k + ICON_PX, 0);
      ctx.stroke();
    }
    ctx.restore();
  }
  path();
  ctx.lineWidth = 5;
  ctx.strokeStyle = color;
  ctx.stroke();
  if (kind === 'q') {
    ctx.fillStyle = color;
    ctx.font = 'bold 34px Arial, Helvetica, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('?', c, c + 2);
  }
  if (kind === 'x') {
    const k = r * 0.5;
    ctx.lineWidth = 5;
    ctx.lineCap = 'round';
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.moveTo(c - k, c - k); ctx.lineTo(c + k, c + k);
    ctx.moveTo(c + k, c - k); ctx.lineTo(c - k, c + k);
    ctx.stroke();
  }
}
