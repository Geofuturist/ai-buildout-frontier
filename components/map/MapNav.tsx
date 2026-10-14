'use client';

import Link from 'next/link';

// The map page has no top bar: the site links sit on the map, top right (SPEC_WEB r8 0.5 p.3).
const LINKS = [
  { href: '/', label: 'Map', current: true },
  { href: '/data/', label: 'Data' },
  { href: '/methodology/', label: 'Methodology' },
  { href: '/attribution/', label: 'Sources' },
  { href: '/about/', label: 'About' },
];

export default function MapNav({ preview }: { preview: boolean }) {
  return (
    <div className="pointer-events-none absolute left-3 right-3 top-3 z-30 flex flex-col items-start gap-1.5 md:left-auto md:flex-row md:items-center">
      {/* Phone: the project name is not in a bar any more; it sits on the map, above the links */}
      <Link href="/" className="pointer-events-auto rounded-md bg-surface px-2 py-1 text-[13px] font-semibold text-ink no-underline shadow-sm md:hidden">
        AI Buildout Frontier{preview && <span className="ml-1 font-normal text-ink2">· preview</span>}
      </Link>
      <nav aria-label="Main" className="pointer-events-auto flex flex-wrap items-center gap-1.5">
      {preview && (
        <span className="hidden rounded-md bg-[#fff4d6] px-2 py-1.5 text-[11px] font-medium text-ink md:inline">Preview · dev data</span>
      )}
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          aria-current={l.current ? 'page' : undefined}
          className={`inline-flex h-8 items-center rounded-md border bg-surface px-2.5 text-[13px] font-bold uppercase tracking-[0.06em] no-underline shadow-sm hover:text-accent ${
            l.current ? 'border-accent text-accent' : 'border-line text-ink2'
          }`}
        >
          {l.label}
        </Link>
      ))}
      </nav>
    </div>
  );
}
