'use client';

import Link from 'next/link';
import CopyButton from '@/components/CopyButton';
import { checkedByLine, isoDate } from '@/lib/format';
import { Downloads } from './parts';
import { ItemsCard, PlaceCard, RecordShell } from './RecordViews';
import Shell from './Shell';
import type { CardState, MapData } from './types';

export default function InfoCard({ data, card, onClose }: { data: MapData; card: CardState; onClose: () => void }) {
  if (!card) return null;
  const layer = data.layers.find((l) => l.layer_id === card.layerId);
  if (!layer) return null;
  const meta = data.metas[layer.meta_id];
  const anchor = data.anchors[layer.layer_id];

  if (card.type === 'layer') {
    const doi = data.datasets[layer.dataset].doi;
    return (
      <Shell title={layer.title} subtitle={`${layer.level} · ${meta.release.dataset} v${meta.release.version}`} onClose={onClose}>
        <p className="mt-2">{meta.description}</p>
        <p className="mt-3"><strong>Coverage.</strong> {meta.coverage.geography}</p>
        {meta.coverage.known_gaps.length > 0 && (
          <>
            <p className="mt-3 font-semibold">Known gaps</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-ink2">
              {meta.coverage.known_gaps.map((g) => <li key={g}>{g}</li>)}
            </ul>
          </>
        )}
        <p className="mt-3"><strong>Freshness.</strong> Data through {meta.freshness.source_current_through ?? 'n/a'} · built {isoDate(meta.freshness.built_at)} · updates: {meta.freshness.source_cadence}</p>
        <p className="mt-3"><strong>License.</strong> <a href={meta.license.url}>{meta.license.name}</a></p>
        <blockquote className="mt-1 border-l-4 border-line pl-3 text-xs text-ink2">{meta.license.attribution_text}</blockquote>
        <p className="mt-3">{checkedByLine(meta)}</p>
        <Downloads layer={layer} />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <CopyButton text={meta.citation.text} label="Cite this layer" />
          {anchor && <Link href={`/methodology/#${anchor}`}>Methodology →</Link>}
        </div>
        {doi && <p className="mt-3 text-xs text-muted">DOI <a href={`https://doi.org/${doi}`}>{doi}</a></p>}
      </Shell>
    );
  }

  // Several objects of one layer at the same spot (Epoch): a list of all of them
  if (card.type === 'records') return <ItemsCard key={card.items.map((x) => String(x.record_id)).join('|')} data={data} layer={layer} items={card.items} onClose={onClose} />;

  // A place of the places layer: its record (one) or the list of its records (several)
  if (meta.display?.count_field) return <PlaceCard key={String(card.props.record_id)} data={data} layer={layer} props={card.props} onClose={onClose} />;

  return <RecordShell data={data} layer={layer} props={card.props} onClose={onClose} />;
}
