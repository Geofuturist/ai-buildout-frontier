// Small shared helpers (safe on server and client).
import type { Meta } from './data';

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} kB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function formatNumber(v: number, maxFrac = 1): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: maxFrac });
}

export function isoDate(s: string | null | undefined): string {
  return s ? s.slice(0, 10) : '';
}

export function doiUrl(doi: string | null): string | null {
  return doi ? `https://doi.org/${doi}` : null;
}

/** "data through 2025" label for the layer list. */
export function throughLabel(meta: Meta): string {
  const d = meta.freshness.source_current_through;
  return d ? `data through ${d.slice(0, 4)}` : 'date varies';
}

const BASE_LABEL: Record<string, string> = {
  source_as_is: 'source as is',
  script_rules: 'script rules',
  human: 'human',
};

/** "Checked by: source as is · 5 automated checks" (SPEC_WEB 4.4). */
export function checkedByLine(meta: Meta): string {
  const lv = meta.verification.levels;
  const base = (['source_as_is', 'script_rules', 'human'] as const)
    .filter((k) => (lv[k] ?? 0) > 0)
    .sort((a, b) => (lv[b] ?? 0) - (lv[a] ?? 0));
  const parts: string[] = [];
  if (base.length === 1 && lv[base[0]] >= 0.9995) parts.push(BASE_LABEL[base[0]]);
  else for (const k of base) parts.push(`${BASE_LABEL[k]} ${Math.round(lv[k] * 100)}%`);
  const agent = lv.agent_sample ?? 0;
  if (agent > 0) parts.push(`agent re-checked ${Math.round(agent * 100)}%`);
  const n = meta.verification.automated_checks.length;
  const checks = n > 0 ? ` · ${n} automated check${n === 1 ? '' : 's'}` : '';
  return `Checked by: ${parts.join(' · ') || 'not recorded'}${checks}`;
}

/** Text of "Cite this record" (SPEC_WEB 4.5). */
export function recordCitation(meta: Meta, key: string): string {
  return meta.citation.record_pattern.replace('{record_key}', key);
}
