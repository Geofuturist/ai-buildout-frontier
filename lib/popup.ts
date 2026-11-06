// The window of an object made of its own fields (display.popup, SPEC_GEM_plants r7 3b W3). The meta gives the rows:
// text with {field} places, an optional condition, a link. Nothing is counted here: a value is what the tiles hold.
// Numbers are formatted for reading only (thousands, one decimal for a non-integer); a field whose unit says "year"
// is written as it is.
import type { FieldDef, Meta, PopupRow, PopupWhen } from './data';

type Props = Record<string, unknown>;

export type PopupLine = { kind: 'text'; text: string } | { kind: 'link'; text: string; href: string };

const empty = (v: unknown) => v === null || v === undefined || v === '';

function asNumber(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/**
 * A value as it is read in the window, by the type of the field in the meta: "number" has one decimal and thousands
 * ("1,234.6"); an integer is written as it is (a year stays "2005") and gets thousands only from 10,000.
 */
export function popupValue(field: FieldDef | undefined, v: unknown): string {
  if (typeof v !== 'number') return String(v);
  if (field?.unit && /year/i.test(field.unit)) return String(v);
  if (field?.type === 'number' || !Number.isInteger(v)) return v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return Math.abs(v) >= 10000 ? v.toLocaleString('en-US') : String(v);
}

/** The condition of a row. Only these tests exist; anything else makes the row hidden, never guessed. */
export function popupWhen(w: PopupWhen | undefined, p: Props): boolean {
  if (!w) return true;
  const v = p[w.field];
  let tested = false;
  if (w.nonempty !== undefined) { tested = true; if (w.nonempty !== !empty(v)) return false; }
  if (w.gt !== undefined) { tested = true; const n = asNumber(v); if (n === null || !(n > w.gt)) return false; }
  if (w.contains !== undefined) { tested = true; if (empty(v) || !String(v).includes(w.contains)) return false; }
  if (w.equals !== undefined) {
    tested = true;
    const n = asNumber(v);
    const same = typeof w.equals === 'number' ? n !== null && n === w.equals : String(v) === String(w.equals);
    if (!same) return false;
  }
  if (w.ne_field !== undefined) { tested = true; const o = p[w.ne_field]; if (empty(v) || empty(o) || String(v) === String(o)) return false; }
  return tested;
}

/** `{field}` places filled from the object; undefined when a place has no value (the row is not shown). */
export function fillTemplate(t: string, p: Props, fields: FieldDef[]): string | undefined {
  let missing = false;
  const out = t.replace(/\{([A-Za-z0-9_]+)\}/g, (_m, name: string) => {
    const v = p[name];
    if (empty(v)) { missing = true; return ''; }
    return popupValue(fields.find((f) => f.name === name), v);
  });
  return missing ? undefined : out;
}

export function popupLines(meta: Meta, p: Props): PopupLine[] {
  const out: PopupLine[] = [];
  for (const row of meta.display?.popup ?? []) {
    if (!popupWhen((row as PopupRow).when, p)) continue;
    if ('link' in row) {
      const href = p[row.link];
      if (typeof href === 'string' && /^https?:\/\//.test(href)) out.push({ kind: 'link', text: row.text, href });
    } else {
      const text = fillTemplate(row.text, p, meta.fields);
      if (text !== undefined) out.push({ kind: 'text', text });
    }
  }
  return out;
}

export function popupTitle(meta: Meta, p: Props): string | undefined {
  const t = meta.display?.popup_title;
  return t ? fillTemplate(t, p, meta.fields) : undefined;
}
