import type { Metadata } from 'next';
import SiteHeader from '@/components/SiteHeader';
import SiteFooter from '@/components/SiteFooter';
import { getData } from '@/lib/data';
import { orderedDatasetNames } from '@/lib/layers';
import type { AttributionSource } from '@/lib/data';

export const metadata: Metadata = {
  title: 'Sources and licences',
  description: 'Publisher, edition, licence and attribution text of every source used in the layers.',
};

const GROUP_TITLE: Record<string, string> = {
  public_domain: 'Public domain',
  attribution: 'Attribution licences',
  share_alike: 'Share-alike licences',
};

function SourceBlock({ s }: { s: AttributionSource }) {
  return (
    <article id={s.source_id} className="my-6 border-t border-line pt-4">
      <h3>
        {s.publisher} <span className="font-normal text-ink2">— {s.product}</span>
      </h3>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted">Edition</dt>
        <dd>{s.edition}</dd>
        <dt className="text-muted">Data through</dt>
        <dd>{s.current_through ?? 'not applicable'}</dd>
        <dt className="text-muted">Source page</dt>
        <dd><a href={s.url}>{s.url}</a></dd>
        <dt className="text-muted">Licence</dt>
        <dd><a href={s.license.url}>{s.license.name}</a> <span className="text-muted">({s.license.id})</span></dd>
        <dt className="text-muted">Basis for publishing</dt>
        <dd>{s.rights_basis_text}</dd>
        <dt className="text-muted">Used in</dt>
        <dd>{s.layers.join('; ')}</dd>
      </dl>
      <p className="mt-3 text-sm text-muted">Attribution text:</p>
      <blockquote className="mt-1 border-l-4 border-line pl-3 text-sm">{s.license.attribution_text}</blockquote>
    </article>
  );
}

export default function AttributionPage() {
  const data = getData();
  const total = data.attribution.reduce((n, g) => n + g.sources.length, 0);
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <div className="prose-abf">
          <h1>Sources and licences</h1>
          <p>
            Each layer keeps its source&apos;s licence; our code is MIT; our own compilations are CC BY 4.0.
            This page is generated from the metadata of the published layers ({total} data sources), so it cannot differ from the data.
          </p>

          <p className="text-sm">
            Datasets covered:{' '}
            {orderedDatasetNames(data).map((n, i) => {
              const d = data.datasets[n];
              return (
              <span key={d.dataset}>
                {i > 0 ? '; ' : ''}
                {d.dataset} v{d.version}
                {d.doi ? <> (DOI <a href={`https://doi.org/${d.doi}`}>{d.doi}</a>)</> : ' (DOI not assigned yet)'}
              </span>
              );
            })}
            .
          </p>

          {data.attribution.map((g) => (
            <section key={g.family}>
              <h2>{GROUP_TITLE[g.family]}</h2>
              {g.sources.map((s) => <SourceBlock key={s.source_id} s={s} />)}
            </section>
          ))}

          <section>
            <h2>Base map</h2>
            <article className="my-6 border-t border-line pt-4">
              <p>
                The background map is drawn from vector tiles served by <a href="https://openfreemap.org">OpenFreeMap</a>,
                {' '}built from <a href="https://openmaptiles.org/">OpenMapTiles</a> with data from{' '}
                <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (ODbL).
                The map style is our own. It carries no administrative boundaries: borders on the map come only from the boundary set above.
              </p>
              <blockquote className="mt-1 border-l-4 border-line pl-3 text-sm">
                © OpenFreeMap © OpenMapTiles Data from OpenStreetMap
              </blockquote>
            </article>
          </section>

          <section>
            <h2>Boundaries and points of view</h2>
            <p>
              Boundaries follow the US government&apos;s point of view and do not express a position of the project.
              Areas that belong to no country in this view are drawn with a neutral fill.
            </p>
          </section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
