import Link from 'next/link';
import { getData } from '@/lib/data';

const LINKS = [
  { href: '/', label: 'Map' },
  { href: '/data/', label: 'Data' },
  { href: '/methodology/', label: 'Methodology' },
  { href: '/attribution/', label: 'Sources' },
  { href: '/about/', label: 'About' },
];

export default function SiteHeader() {
  const data = getData();
  return (
    <header className="shrink-0 border-b border-line bg-surface">
      {data.channel === 'dev' && (
        <div className="bg-[#fff4d6] px-3 py-1 text-center text-xs text-ink">
          Preview build: data from the dev channel. Not the published release.
        </div>
      )}
      <div className="flex min-h-[48px] items-center justify-between gap-3 px-3 sm:px-4">
        <Link href="/" className="font-semibold text-ink no-underline">
          <span className="hidden sm:inline">AI Buildout Frontier</span>
          <span className="sm:hidden">ABF</span>
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1 text-sm">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="inline-flex min-h-[44px] items-center px-2 text-ink2 no-underline hover:text-accent">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
