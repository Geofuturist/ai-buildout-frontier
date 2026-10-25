'use client';

// Windows of point records (SPEC_DC_world_v0_2_0 4.2 and 4.4):
//  - RecordShell: the window of one record;
//  - RecordList: a list of records, a row opens the window of that record;
//  - ItemsCard: several objects of one layer at the same spot (Epoch: up to 3 sites in one point);
//  - PlaceCard: a place of the places layer: one record -> its window, more -> the list of its records.
// Nothing is counted here: lists are what the tiles or the published CSV hold.
import { useEffect, useState } from 'react';
import Link from 'next/link';
import CopyButton from '@/components/CopyButton';
import type { LayerEntry } from '@/lib/data';
import { checkedByLine, recordCitation } from '@/lib/format';
import { capitalize, recordNoun, unitWord } from '@/lib/layers';
import { GROUPS_FILE, PLACE_KEY, loadPlaceIndex, loadTypeGroups, placeRowsLayer, rowsOfGroup, rowsOfPlace } from '@/lib/placeRows';
import { filterColumn } from '@/lib/pointSize';
import { epochTags, parseLinks } from '@/lib/dcTexts';
import DcPointRows, { capacityShort, str } from './DcPointRows';
import { MODULE_BY_TYPE } from './modules';
import { ValueRows, sourceLine } from './parts';
import RecordDownload from './RecordDownload';
import Shell from './Shell';
import type { MapData } from './types';

type Props = Record<string, unknown>;

const BACK = 'text-xs text-accent hover:underline';

/** The window of one record: its rows, source, licence, download, citation. `onBack` adds a way back to a list. */
export function RecordShell({ data, layer, props: p, onClose, onBack }: { data: MapData; layer: LayerEntry; props: Props; onClose: () => void; onBack?: () => void }) {
  const meta = data.metas[layer.meta_id];
  const anchor = data.anchors[layer.layer_id];
  const mod = MODULE_BY_TYPE[layer.tiles.geometry_type];
  const key = String(p[mod.keyField] ?? '');
  const noun = recordNoun(layer);
  const title = typeof p.name === 'string' && p.name ? p.name : `${capitalize(noun)} ${key}`;
  return (
    <Shell title={title} subtitle={`${key} · ${layer.title}`} onClose={onClose}>
      {onBack && (
        <button type="button" className={`mt-2 ${BACK}`} onClick={onBack}>
          ← Back to the list
        </button>
      )}
      {meta.display?.size_field ? (
        <DcPointRows layer={layer} meta={meta} props={p} anchor={anchor} />
      ) : (
        <ValueRows layer={layer} meta={meta} props={p} keyField={mod.keyField} />
      )}
      <p className="mt-4 text-xs text-ink2">{sourceLine(meta)}</p>
      <p className="mt-1 text-xs text-ink2">License: <a href={meta.license.url}>{meta.license.name}</a></p>
      <p className="mt-1 text-xs text-ink2">{checkedByLine(meta)}</p>
      {mod.recordDownload && key && <RecordDownload layer={layer} meta={meta} keyField={mod.keyField} keyValue={key} />}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <CopyButton text={recordCitation(meta, key)} label={mod.recordDownload ? 'Cite this record' : `Cite this ${noun}`} />
        {anchor && <Link href={`/methodology/#${anchor}`}>Methodology →</Link>}
      </div>
      <p className="mt-3 text-sm"><Link href={`/data/#${layer.layer_id}`}>All files of this layer</Link></p>
    </Shell>
  );
}

/** Rows of a list: name, who (operator or owner), status, class or power, links. A row opens the window of its record. */
export function RecordList({ data, layer, items, onOpen }: { data: MapData; layer: LayerEntry; items: Props[]; onOpen: (i: number) => void }) {
  const meta = data.metas[layer.meta_id];
  const keyField = MODULE_BY_TYPE[layer.tiles.geometry_type].keyField;
  return (
    <ul className="mt-2">
      {items.map((p, i) => {
        const key = String(p[keyField] ?? i);
        const who = str(p.operator) || epochTags(str(p.owner));
        const line = [who, str(p.status_raw), meta.display?.size_field ? capacityShort(meta, p) : ''].filter(Boolean).join(' · ');
        const links = parseLinks(str(p.source_urls) || str(p.selected_sources));
        return (
          <li key={key} className="border-t border-line py-2">
            <button type="button" className="block min-h-[44px] w-full text-left" onClick={() => onOpen(i)}>
              <span className="block font-semibold text-ink">{str(p.name) || key}</span>
              {line && <span className="block text-xs text-ink2">{line}</span>}
            </button>
            {links.length > 0 && (
              <p className="mt-0.5 break-all text-xs text-ink2">
                Sources:{' '}
                {links.slice(0, 2).map((l, j) => (
                  <span key={l.href}>
                    {j > 0 && ', '}
                    <a href={l.href} target="_blank" rel="noopener noreferrer">{l.label}</a>
                  </span>
                ))}
                {links.length > 2 && ` and ${links.length - 2} more in the record`}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Objects of one layer at the same spot, taken from the tiles. */
export function ItemsCard({ data, layer, items, onClose }: { data: MapData; layer: LayerEntry; items: Props[]; onClose: () => void }) {
  const [open, setOpen] = useState<number | null>(null);
  if (open !== null && items[open]) return <RecordShell data={data} layer={layer} props={items[open]} onClose={onClose} onBack={() => setOpen(null)} />;
  return (
    <Shell title={`${items.length} ${unitWord(layer)} at this spot`} subtitle={layer.title} onClose={onClose}>
      <RecordList data={data} layer={layer} items={items} onOpen={setOpen} />
    </Shell>
  );
}

/** A place of the places layer: the records come from the published CSV of the layer of records, by the place key. */
export function PlaceCard({ data, layer, props: p, typeFilter, onClose }: { data: MapData; layer: LayerEntry; props: Props; typeFilter: string | null; onClose: () => void }) {
  const meta = data.metas[layer.meta_id];
  const rowsLayer = placeRowsLayer(layer, data.layers, data.metas);
  const rowsMeta = rowsLayer ? data.metas[rowsLayer.meta_id] : undefined;
  const csvUrl = rowsLayer?.files.csv?.url;
  const n = Number(p[meta.display?.count_field ?? '']);
  const ref = str(p[PLACE_KEY]);
  // Filter by type: the list shows the records of the chosen group, from the groups file of the layer
  const column = filterColumn(meta.display ?? {}, typeFilter);
  const groupsUrl = layer.extra_files.find((f) => f.path === GROUPS_FILE)?.url;
  const nGroup = column ? Number(p[column]) : n;
  const [state, setState] = useState<'loading' | 'error' | { rows: Props[]; all: number }>('loading');
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    setState('loading');
    setOpen(null);
    if (!csvUrl || !rowsMeta || !ref) {
      console.error(`place ${ref || '?'}: the layer of its records, its CSV or the place key is missing`);
      setState('error');
      return;
    }
    Promise.all([loadPlaceIndex(csvUrl), column && groupsUrl ? loadTypeGroups(groupsUrl) : Promise.resolve(null)])
      .then(([idx, groups]) => {
        const all = rowsOfPlace(idx, ref, rowsMeta);
        // The list is not hidden if the numbers differ: the difference is reported, and the rows are shown
        if (all.length !== n) console.error(`place ${ref}: the places layer gives ${n} records, the file of records lists ${all.length}`);
        let rows = all;
        if (column && typeFilter) {
          if (groups) {
            rows = rowsOfGroup(all, groups, typeFilter);
            if (rows.length !== nGroup) console.error(`place ${ref}: the places layer gives ${nGroup} records of the type, the file of records lists ${rows.length}`);
          } else console.error(`place ${ref}: ${GROUPS_FILE} is missing, the list shows all records of the place`);
        }
        if (live) setState({ rows, all: all.length });
      })
      .catch((e) => {
        console.error(`place ${ref}: could not read the records (${e instanceof Error ? e.message : String(e)})`);
        if (live) setState('error');
      });
    return () => {
      live = false;
    };
  }, [csvUrl, rowsMeta, ref, n, column, groupsUrl, typeFilter, nGroup]);

  const title = str(p.place_name) || ref;
  const subtitle = `${ref} · ${layer.title}`;
  if (state === 'loading') {
    return (
      <Shell title={title} subtitle={subtitle} onClose={onClose}>
        <p className="mt-3 text-ink2">Loading the records…</p>
      </Shell>
    );
  }
  if (state === 'error' || state.rows.length === 0 || !rowsLayer) {
    return (
      <Shell title={title} subtitle={subtitle} onClose={onClose}>
        <p role="alert" className="mt-3 text-[#9a2a00]">Could not read the records of this place.</p>
        <p className="mt-3 text-sm"><Link href={`/data/#${layer.layer_id}`}>All files of this layer</Link></p>
      </Shell>
    );
  }
  const rows = state.rows;
  if (rows.length === 1) return <RecordShell data={data} layer={rowsLayer} props={rows[0]} onClose={onClose} />;
  if (open !== null && rows[open]) return <RecordShell data={data} layer={rowsLayer} props={rows[open]} onClose={onClose} onBack={() => setOpen(null)} />;
  const d = meta.display;
  const listTitle = d?.list_title ? d.list_title.replace('{n}', String(rows.length)).replace('{place_name}', title) : `${rows.length} ${unitWord(rowsLayer)} at this place`;
  const groupLabel = typeFilter ? d?.legend_type_labels?.[typeFilter] ?? typeFilter : '';
  return (
    <Shell title={title} subtitle={subtitle} onClose={onClose}>
      <p className="mt-2 text-ink2">{listTitle}</p>
      {d?.list_note && <p className="mt-1 text-xs text-muted">{d.list_note}</p>}
      {column && state.rows.length !== state.all && <p className="mt-1 text-xs text-ink2">Filter: {groupLabel}. {state.rows.length} of the {state.all} records of this place.</p>}
      <RecordList data={data} layer={rowsLayer} items={rows} onOpen={setOpen} />
      <p className="mt-3 text-sm"><Link href={`/data/#${rowsLayer.layer_id}`}>All files of the records</Link></p>
    </Shell>
  );
}
