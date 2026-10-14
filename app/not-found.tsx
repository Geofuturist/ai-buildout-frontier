import Link from 'next/link';
import SiteHeader from '@/components/SiteHeader';
import SiteFooter from '@/components/SiteFooter';

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 prose-abf">
        <h1>Page not found</h1>
        <p>This address does not exist on the site. Try the <Link href="/">map</Link>, the <Link href="/data/">data catalog</Link> or the <Link href="/methodology/">methodology</Link>.</p>
      </main>
      <SiteFooter />
    </>
  );
}
