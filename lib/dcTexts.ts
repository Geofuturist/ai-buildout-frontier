// Texts of the point window of the world data-center layers (RES_texts_DC section 7, SPEC_DC_world section 6).
// Chosen by the kind of the size field (classes or numbers), never by a layer id.
import { sizeLabels } from './pointSize';

/** "10–99 MW · size class given by the Atlas; basis not stated" */
export function classCapacity(cls: string, classes: string[], breaks: number[], unit: string): string {
  const i = classes.indexOf(cls);
  const label = i >= 0 ? sizeLabels(breaks, unit)[i] : cls;
  return `${label} · size class given by the Atlas; basis not stated`;
}
export const CAPACITY_UNKNOWN_CLASS = 'Capacity: unknown — not given by the Atlas';
export const CAPACITY_UNKNOWN_NUMBER = 'Capacity: unknown — not given by Epoch AI';
export const CAPACITY_WITHHELD = 'Capacity: not published for this site — another layer of the project gives a different basis for it';

/** "120 MW · current IT power, Epoch AI, file of 12 Oct 2026" and the zero form */
export function numberCapacity(mw: number, unit: string, fileDate: string): string {
  const file = fileDate ? `, file of ${fileDate}` : '';
  if (mw === 0) return `0 ${unit} · no IT power in operation yet (Epoch AI${file})`;
  return `${mw.toLocaleString('en-US', { maximumFractionDigits: 1 })} ${unit} · current IT power, Epoch AI${file}`;
}

/** "2026-10-12" -> "12 Oct 2026" */
export function longDate(iso: string | null | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!m) return '';
  const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m[2]) - 1];
  return `${Number(m[3])} ${mon} ${m[1]}`;
}

/** Epoch's confidence tags in words: "Alibaba #confident" -> "Alibaba (Epoch: confident)" */
export function epochTags(text: string): string {
  return text.replace(/\s*#(confident|likely|speculative)\b/gi, (_m, t: string) => ` (Epoch: ${t.toLowerCase()})`).trim();
}

export interface SourceLink {
  href: string;
  label: string;
}

/** Links of a record: ';'-separated URLs (Atlas) or Markdown links separated by ' | ' (Epoch). Only http(s). */
export function parseLinks(raw: string): SourceLink[] {
  const out: SourceLink[] = [];
  const md = /\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g;
  let m: RegExpExecArray | null;
  let any = false;
  while ((m = md.exec(raw))) {
    any = true;
    out.push({ href: m[2], label: m[1].trim() || hostOf(m[2]) });
  }
  if (!any) {
    for (const part of raw.split(';')) {
      const u = part.trim();
      if (/^https?:\/\/\S+$/i.test(u)) out.push({ href: u, label: hostOf(u) });
    }
  }
  return out;
}

function hostOf(u: string): string {
  try {
    return new URL(u).hostname.replace(/^www\./, '');
  } catch {
    return u;
  }
}
