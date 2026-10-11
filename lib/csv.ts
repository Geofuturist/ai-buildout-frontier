// Cutting one record out of a published layer CSV (SPEC_WEB 0.2). Runs in the browser; no server.
// The raw text of the header and of the row is reused as is, so values are never re-formatted.

/** Offsets [start, end) of every non-empty CSV record; quoted fields may contain line breaks. */
export function scanRecords(text: string): [number, number][] {
  const out: [number, number][] = [];
  const n = text.length;
  let start = 0;
  let inQuotes = false;
  for (let i = 0; i < n; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') i++;
        else inQuotes = false;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === '\n' || c === '\r') {
      if (i > start) out.push([start, i]);
      if (c === '\r' && text[i + 1] === '\n') i++;
      start = i + 1;
    }
  }
  if (start < n) out.push([start, n]);
  return out;
}

/** Splits one raw CSV record into unquoted field values. */
export function splitFields(raw: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (inQuotes) {
      if (c === '"') {
        if (raw[i + 1] === '"') {
          cur += '"';
          i++;
        } else inQuotes = false;
      } else cur += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ',') {
      out.push(cur);
      cur = '';
    } else cur += c;
  }
  out.push(cur);
  return out;
}

export interface RecordCut {
  header: string;
  row: string;
  eol: string;
}

/** Finds the row whose column `keyColumn` equals `key`. Returns null if the column or the row is missing. */
export function cutRecord(text: string, keyColumn: string, key: string): RecordCut | null {
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const recs = scanRecords(src);
  if (recs.length < 2) return null;
  const header = src.slice(recs[0][0], recs[0][1]);
  const col = splitFields(header).indexOf(keyColumn);
  if (col < 0) return null;
  for (let r = 1; r < recs.length; r++) {
    const raw = src.slice(recs[r][0], recs[r][1]);
    if (splitFields(raw)[col] === key) return { header, row: raw, eol: src.includes('\r\n') ? '\r\n' : '\n' };
  }
  return null;
}

/** "# Cite: ..." / "# Source: ..." lines, then the header and the single row. */
export function buildRecordCsv(cut: RecordCut, cite: string, sources: string[]): string {
  const one = (s: string) => s.replace(/\s+/g, ' ').trim();
  // attribution texts usually start with "Source:" already
  const src = (s: string) => one(s).replace(/^Source:\s*/i, '');
  const lines = [`# Cite: ${one(cite)}`, ...sources.map((s) => `# Source: ${src(s)}`), cut.header, cut.row];
  return lines.join(cut.eol) + cut.eol;
}

/** A file-name-safe piece. */
export function safePart(s: string): string {
  return s.replace(/[^A-Za-z0-9._-]+/g, '_');
}
