import type { Metadata } from 'next';
import Link from 'next/link';
import SiteHeader from '@/components/SiteHeader';
import SiteFooter from '@/components/SiteFooter';
import CopyButton from '@/components/CopyButton';
import { orderedDatasetNames } from '@/lib/layers';
import { getData } from '@/lib/data';
import type { FileRef, LayerEntry, Meta } from '@/lib/data';
import { checkedByLine, doiUrl, formatBytes, isoDate } from '@/lib/format';

export const metadata: Metadata = {
  title: 'Data',
  description: 'Catalogue of all published layers: versions, DOIs, citations and download links with sizes and checksums.',
};

const FORMAT_LABEL: Record<string, string> = {
  parquet: 'GeoParquet',
  'geojson.gz': 'GeoJSON (gzip)',
  csv: 'CSV (no geometry)',
  pmtiles: 'Map tiles (display only)',
};
const FORMAT_ORDER = ['parquet', 'geojson.gz', 'csv', 'pmtiles'];

function FileRow({ label, f, kind }: { label: string; f: FileRef; kind: string }) {
  return (
    <tr>
      <td>{label}</td>
      <td>{kind}</td>
      <td className="text-right">{formatBytes(f.bytes)}</td>
      <td><code title={f.sha256}>{f.sha256.slice(0, 12)}</code></td>
      <td><a href={f.url}>{f.path.split('/').pop()}</a></td>
    </tr>
  );
}

function LayerCard({ meta, entries }: { meta: Meta; entries: LayerEntry[] }) {
  const data = getData();
  const anchor = data.anchors[entries[0].layer_id];
  const levels = meta.levels ? meta.levels.join(', ') : meta.level;
  const multi = entries.length > 1;
  return (
    <article id={meta.layer_id} className="my-8 border-t border-line pt-4">
      <h3>{meta.title}</h3>
      <p className="mt-1"><span className="chip">{levels}</span></p>
      <p>{meta.description}</p>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted">Coverage</dt>
        <dd>{meta.coverage.geography}{meta.coverage.n_records ? ` · ${meta.coverage.n_records.toLocaleString('en-US')} records` : ''}</dd>
        <dt className="text-muted">Data through</dt>
        <dd>{meta.freshness.source_current_through ?? 'varies by country'} · built {isoDate(meta.freshness.built_at)} · updates: {meta.freshness.source_cadence}</dd>
        <dt className="text-muted">Licence</dt>
        <dd><a href={meta.license.url}>{meta.license.name}</a></dd>
        <dt className="text-muted">Checking</dt>
        <dd>{checkedByLine(meta).replace('Checked by: ', '')}</dd>
      </dl>

      <div className="table-wrap mt-4">
        <table>
          <thead>
            <tr><th>{multi ? 'Part' : 'Layer'}</th><th>Format</th><th className="text-right">Size</th><th>SHA-256</th><th>File</th></tr>
          </thead>
          <tbody>
            {entries.map((e) =>
              FORMAT_ORDER.filter((fmt) => e.files[fmt]).map((fmt) => (
                <FileRow key={`${e.layer_id}-${fmt}`} label={multi ? e.title : meta.title} f={e.files[fmt]} kind={FORMAT_LABEL[fmt]} />
              )),
            )}
            {entries.flatMap((e) => e.extra_files).map((f) => (
              <FileRow key={f.path} label="Supporting file" f={f} kind={f.description ?? 'Other'} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-sm text-muted">Citation</p>
      <p className="mt-1 text-sm">{meta.citation.text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <CopyButton text={meta.citation.text} label="Cite this layer" />
        {anchor && <Link href={`/methodology/#${anchor}`}>Methodology for this layer →</Link>}
      </div>
    </article>
  );
}

export default function DataPage() {
  const data = getData();
  // the default layer's country first, then by country name; boundaries last (SPEC_WEB 0.3 p.6)
  const order = orderedDatasetNames(data);
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">
        <div className="prose-abf">
          <h1>Data</h1>
          <p>
            Every layer is a downloadable file with a fixed, versioned address. Map tiles are for display only; use GeoParquet, GeoJSON or CSV for analysis.
            Read codes as text (for example <code>unit_id</code>) or leading zeros disappear.
          </p>

          {order.map((name) => {
            const ds = data.datasets[name];
            const entries = data.layers.filter((l) => l.dataset === name);
            const metaIds = [...new Set(entries.map((e) => e.meta_id))];
            const doi = doiUrl(ds.doi);
            return (
              <section key={name}>
                <h2>{name} <span className="font-normal text-ink2">v{ds.version}</span></h2>
                <p className="text-sm">
                  DOI: {doi ? <a href={doi}>{ds.doi}</a> : 'not assigned'} · tag <code>{ds.tag}</code> · published {ds.published_at}
                  {ds.boundary_release ? <> · boundaries: <code>{ds.boundary_release}</code></> : null}
                </p>
                {metaIds.map((id) => (
                  <LayerCard key={id} meta={data.metas[id]} entries={entries.filter((e) => e.meta_id === id)} />
                ))}
                {(ds.extra_files.length > 0 || ds.source_archives.length > 0) && (
                  <>
                    <h3>Supporting files of {name}</h3>
                    <div className="table-wrap">
                      <table>
                        <thead><tr><th>Type</th><th>Description</th><th className="text-right">Size</th><th>SHA-256</th><th>File</th></tr></thead>
                        <tbody>
                          {[...ds.source_archives.map((f) => ({ f, t: 'Source archive' })), ...ds.extra_files.map((f) => ({ f, t: 'Reference' }))].map(({ f, t }) => (
                            <tr key={f.path}>
                              <td>{t}</td>
                              <td>{f.description}</td>
                              <td className="text-right">{formatBytes(f.bytes)}</td>
                              <td><code title={f.sha256}>{f.sha256.slice(0, 12)}</code></td>
                              <td><a href={f.url}>{f.path.split('/').pop()}</a></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </section>
            );
          })}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
