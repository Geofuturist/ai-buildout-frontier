// app/components/DCPopup.tsx
// Datacenter popup component — renders inside react-map-gl <Popup>.
// Three content variants: frontier-circles, clusters-points, osm-points.

'use client';

import { Popup } from 'react-map-gl/maplibre';
import { DC_STATUS_COLORS, type DCStatus } from '@/lib/queries/datacenters';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DCPopupProps {
  layer: 'frontier-circles' | 'clusters-points' | 'osm-points';
  coordinates: [number, number];
  properties: Record<string, unknown>;
  onClose: () => void;
}

// ─── Formatting helpers ───────────────────────────────────────────────────────

function formatPower(mw: unknown): string {
  if (mw == null || typeof mw !== 'number') return '—';
  if (mw >= 1000) return `${(mw / 1000).toFixed(1)} GW`;
  return `${mw} MW`;
}

function formatCount(n: unknown): string {
  if (n == null || typeof n !== 'number') return '—';
  return n.toLocaleString('en-US');
}

function superscript(n: number): string {
  const map: Record<string, string> = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
  };
  return n.toString().split('').map((c) => map[c] ?? c).join('');
}

function formatOps(ops: unknown): string {
  if (ops == null || typeof ops !== 'number') return '—';
  const exp = Math.floor(Math.log10(ops));
  const mantissa = ops / Math.pow(10, exp);
  return `${mantissa.toFixed(1)} × 10${superscript(exp)}`;
}

function asString(v: unknown): string | null {
  if (v == null) return null;
  return String(v);
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<DCStatus, string> = {
  operational:        'Operational',
  under_construction: 'Under construction',
  planned:            'Planned',
  announced:          'Announced',
  decommissioned:     'Decommissioned',
  unknown:            'Status unknown',
};

function StatusBadge({ status }: { status: DCStatus }) {
  const color = DC_STATUS_COLORS[status] ?? DC_STATUS_COLORS.unknown;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
      style={{ backgroundColor: `${color}22`, color }}
    >
      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

// ─── Row helper ───────────────────────────────────────────────────────────────

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <tr>
      <td className="text-gray-400 pr-3 py-0.5 align-top whitespace-nowrap text-[11px]">{label}</td>
      <td className="text-gray-800 font-medium text-[11px] py-0.5">{value ?? '—'}</td>
    </tr>
  );
}

// ─── Content variants ─────────────────────────────────────────────────────────

function FrontierContent({ p }: { p: Record<string, unknown> }) {
  const status = (p.status ?? 'unknown') as DCStatus;
  const citation = asString(p.citation);
  return (
    <>
      <p className="font-semibold text-[13px] text-gray-900 mb-2 leading-tight">
        {asString(p.name) ?? 'Unnamed datacenter'}
      </p>
      <table className="w-full mb-2">
        <tbody>
          <Row label="Owner" value={asString(p.owner)} />
          <Row label="Country" value={asString(p.country)} />
          <Row label="Status" value={<StatusBadge status={status} />} />
          <Row label="Power" value={formatPower(p.power_capacity_mw)} />
          <Row label="H100 equivalents" value={formatCount(p.h100_equivalent)} />
        </tbody>
      </table>
      {citation && (
        <a
          href={citation}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] text-blue-600 hover:underline"
        >
          Source: Epoch AI Frontier ↗
        </a>
      )}
      {!citation && (
        <span className="text-[11px] text-gray-400">Source: Epoch AI Frontier</span>
      )}
    </>
  );
}

function ClustersContent({ p }: { p: Record<string, unknown> }) {
  const status = (p.status ?? 'unknown') as DCStatus;
  const citation = asString(p.citation);
  return (
    <>
      <p className="font-semibold text-[13px] text-gray-900 mb-2 leading-tight">
        {asString(p.name) ?? 'Unnamed cluster'}
      </p>
      <table className="w-full mb-2">
        <tbody>
          <Row label="Owner" value={asString(p.owner)} />
          <Row label="Country" value={asString(p.country)} />
          <Row label="Status" value={<StatusBadge status={status} />} />
          <Row label="Certainty" value={asString(p.certainty)} />
          <Row label="Power" value={formatPower(p.power_capacity_mw)} />
          <Row label="H100 equivalents" value={formatCount(p.h100_equivalent)} />
          <Row label="Max OP/s" value={formatOps(p.ops_total)} />
        </tbody>
      </table>
      {citation && (
        <a
          href={citation}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] text-blue-600 hover:underline"
        >
          Source: Epoch AI Clusters ↗
        </a>
      )}
      {!citation && (
        <span className="text-[11px] text-gray-400">Source: Epoch AI GPU Clusters</span>
      )}
    </>
  );
}

function OsmContent({ p }: { p: Record<string, unknown> }) {
  return (
    <>
      <p className="font-semibold text-[13px] text-gray-900 mb-2 leading-tight">
        {asString(p.name) ?? 'Unnamed datacenter'}
      </p>
      <table className="w-full mb-2">
        <tbody>
          <Row label="Operator" value={asString(p.operator)} />
        </tbody>
      </table>
      <a
        href="https://www.openstreetmap.org"
        target="_blank"
        rel="noopener noreferrer"
        className="text-[11px] text-blue-600 hover:underline"
      >
        Source: OpenStreetMap ↗
      </a>
    </>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function DCPopup({ layer, coordinates, properties, onClose }: DCPopupProps) {
  return (
    <Popup
      longitude={coordinates[0]}
      latitude={coordinates[1]}
      anchor="bottom"
      onClose={onClose}
      closeOnClick={false}
      maxWidth="320px"
    >
      <div
        style={{
          fontFamily: 'system-ui, sans-serif',
          minWidth: '200px',
          maxWidth: '90vw',
          maxHeight: '60vh',
          overflowY: 'auto',
          padding: '4px 2px',
        }}
      >
        {layer === 'frontier-circles' && <FrontierContent p={properties} />}
        {layer === 'clusters-points'  && <ClustersContent p={properties} />}
        {layer === 'osm-points'       && <OsmContent p={properties} />}
      </div>
    </Popup>
  );
}
