import type { Metadata } from 'next';
import SiteHeader from '@/components/SiteHeader';
import SiteFooter from '@/components/SiteFooter';
import DataBrowser from '@/components/DataBrowser';
import { buildCards } from '@/lib/dataCards';
import { getData } from '@/lib/data';
import { doiUrl } from '@/lib/format';

export const metadata: Metadata = {
  title: 'Data',
  description: 'Catalog of all published layers: versions, DOIs, citations and download links with sizes and checksums.',
};

export default function DataPage() {
  const data = getData();
  const cards = buildCards(data);
  // Datasets of the territory index have no layer cards; their DOI is shown here
  const indexSets = Object.values(data.datasets).filter((d) => d.kind === 'index');
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <div className="prose-abf">
          <h1>Data</h1>
          <p>
            Every layer is a downloadable file with a fixed, versioned address. Choose a topic or a country, open a card for its files.
            Map tiles are for display only; use GeoParquet, GeoJSON or CSV for analysis. Read codes as text (for example <code>unit_id</code>) or leading zeros disappear.
          </p>
        </div>
        {indexSets.length > 0 && (
          <div className="prose-abf mb-6">
            <h2>Territory index</h2>
            <ul>
              {indexSets.map((d) => (
                <li key={d.dataset}>
                  {d.dataset} v{d.version} · {doiUrl(d.doi) ? <a href={doiUrl(d.doi)!}>{d.doi}</a> : 'DOI not assigned'}
                </li>
              ))}
            </ul>
          </div>
        )}
        <DataBrowser cards={cards} />
      </main>
      <SiteFooter />
    </>
  );
}
