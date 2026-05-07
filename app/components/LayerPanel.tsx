// app/components/LayerPanel.tsx
// Layer control panel rendered inside the desktop sidebar and mobile bottom sheet.
// Receives layerState from AppShell (which holds the URL-backed state).

'use client';

import type { ReactNode } from 'react';
import type { LayerState } from '@/lib/hooks/useLayerState';
import { FEASIBILITY_COLORS } from '@/lib/feasibility';
import { DC_STATUS_COLORS, type DCStatus } from '@/lib/queries/datacenters';

// ─── Sub-components ──────────────────────────────────────────────────────────

function LayerGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 mb-2">
        {title}
      </p>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Toggle({
  enabled,
  onToggle,
  size = 'md',
}: {
  enabled: boolean;
  onToggle: (v: boolean) => void;
  size?: 'md' | 'sm';
}) {
  const w = size === 'sm' ? 'w-7 h-4' : 'w-9 h-5';
  const dot = size === 'sm' ? 'w-3 h-3 top-0.5' : 'w-3.5 h-3.5 top-[3px]';
  const translate = size === 'sm' ? 'translate-x-3.5' : 'translate-x-4';
  return (
    <button
      role="switch"
      aria-checked={enabled}
      onClick={() => onToggle(!enabled)}
      className={`relative inline-flex flex-shrink-0 ${w} rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
        enabled ? 'bg-blue-600' : 'bg-gray-200'
      }`}
    >
      <span
        className={`${dot} left-0.5 absolute bg-white rounded-full shadow transition-transform duration-200 ${
          enabled ? translate : 'translate-x-0'
        }`}
      />
    </button>
  );
}

function LayerToggle({
  label,
  sublabel,
  enabled,
  onToggle,
  legend,
  children,
}: {
  label: string;
  sublabel?: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  legend?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={`text-sm font-medium leading-tight ${enabled ? 'text-gray-900' : 'text-gray-400'}`}>
            {label}
          </p>
          {sublabel && (
            <p className={`text-xs mt-0.5 ${enabled ? 'text-gray-500' : 'text-gray-300'}`}>
              {sublabel}
            </p>
          )}
        </div>
        <Toggle enabled={enabled} onToggle={onToggle} />
      </div>

      {/* Optional legend */}
      {legend && enabled && (
        <div className="mt-2 pl-1">{legend}</div>
      )}

      {/* Sub-toggles */}
      {children && (
        <div className={`mt-2 pl-6 space-y-1.5 ${!enabled ? 'opacity-40 pointer-events-none' : ''}`}>
          {children}
        </div>
      )}
    </div>
  );
}

function SubToggle({
  label,
  enabled,
  onToggle,
}: {
  label: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <p className="text-xs text-gray-600 leading-tight">{label}</p>
      <Toggle enabled={enabled} onToggle={onToggle} size="sm" />
    </div>
  );
}

// ─── Legends ─────────────────────────────────────────────────────────────────

const FEASIBILITY_CATEGORIES = [
  { key: 'high_feasibility',    label: 'High' },
  { key: 'moderate_feasibility', label: 'Moderate' },
  { key: 'low_feasibility',     label: 'Low' },
  { key: 'critical_constraint', label: 'Critical' },
  { key: 'dc_hotspot',          label: 'DC Hotspot' },
] as const;

function FeasibilityColorScale() {
  return (
    <div className="flex gap-px rounded overflow-hidden" title="Grid Feasibility Index">
      {FEASIBILITY_CATEGORIES.map(({ key, label }) => (
        <div
          key={key}
          className="flex-1 h-2 relative group"
          style={{ backgroundColor: FEASIBILITY_COLORS[key] }}
          title={label}
        />
      ))}
    </div>
  );
}

const STATUS_DISPLAY: { status: DCStatus; label: string }[] = [
  { status: 'operational',       label: 'Operational' },
  { status: 'under_construction', label: 'Under construction' },
  { status: 'planned',           label: 'Planned' },
  { status: 'announced',         label: 'Announced' },
  { status: 'decommissioned',    label: 'Decommissioned' },
  { status: 'unknown',           label: 'Unknown' },
];

function StatusLegend() {
  return (
    <div className="space-y-1">
      {STATUS_DISPLAY.map(({ status, label }) => (
        <div key={status} className="flex items-center gap-1.5">
          <span
            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: DC_STATUS_COLORS[status] }}
          />
          <span className="text-[11px] text-gray-500">{label}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Source links ─────────────────────────────────────────────────────────────

function SourceLinks() {
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 mb-1">
        Sources
      </p>
      <a
        href="https://epoch.ai/data/frontier-data-centres"
        target="_blank"
        rel="noopener noreferrer"
        className="block text-[11px] text-blue-600 hover:underline"
      >
        Epoch AI Frontier ↗
      </a>
      <a
        href="https://epoch.ai/data/gpu-clusters"
        target="_blank"
        rel="noopener noreferrer"
        className="block text-[11px] text-blue-600 hover:underline"
      >
        Epoch AI GPU Clusters ↗
      </a>
      <a
        href="https://www.openstreetmap.org"
        target="_blank"
        rel="noopener noreferrer"
        className="block text-[11px] text-blue-600 hover:underline"
      >
        OpenStreetMap (ODbL) ↗
      </a>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface LayerPanelProps {
  layerState: LayerState;
}

export default function LayerPanel({ layerState }: LayerPanelProps) {
  const {
    feasibilityEnabled,
    frontierEnabled,
    clustersEnabled,
    osmEnabled,
    frontierShowPlanned,
    frontierShowDecom,
    clustersShowPlanned,
    clustersShowDecom,
    update,
  } = layerState;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Panel header */}
      <div className="px-4 py-3 border-b border-gray-100 flex-shrink-0">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-500">
          Layers
        </h2>
      </div>

      {/* Scrollable layer list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">

        <LayerGroup title="Grid Feasibility">
          <LayerToggle
            label="County feasibility scores"
            sublabel="Virginia, 133 counties"
            enabled={feasibilityEnabled}
            onToggle={(v) => update({ feasibilityEnabled: v })}
            legend={<FeasibilityColorScale />}
          />
        </LayerGroup>

        <LayerGroup title="Datacenters">
          <LayerToggle
            label="Frontier AI"
            sublabel="33 verified locations"
            enabled={frontierEnabled}
            onToggle={(v) => update({ frontierEnabled: v })}
            legend={<StatusLegend />}
          >
            <SubToggle
              label="Show planned / announced"
              enabled={frontierShowPlanned}
              onToggle={(v) => update({ frontierShowPlanned: v })}
            />
            <SubToggle
              label="Show decommissioned"
              enabled={frontierShowDecom}
              onToggle={(v) => update({ frontierShowDecom: v })}
            />
          </LayerToggle>

          <LayerToggle
            label="GPU Clusters"
            sublabel="598 spatial locations"
            enabled={clustersEnabled}
            onToggle={(v) => update({ clustersEnabled: v })}
          >
            <SubToggle
              label="Show planned / announced"
              enabled={clustersShowPlanned}
              onToggle={(v) => update({ clustersShowPlanned: v })}
            />
            <SubToggle
              label="Show decommissioned"
              enabled={clustersShowDecom}
              onToggle={(v) => update({ clustersShowDecom: v })}
            />
          </LayerToggle>

          <LayerToggle
            label="All datacenters (OSM, US)"
            sublabel="1,317 locations"
            enabled={osmEnabled}
            onToggle={(v) => update({ osmEnabled: v })}
          />
        </LayerGroup>
      </div>

      {/* Footer with source links */}
      <div className="px-4 py-4 border-t border-gray-100 flex-shrink-0">
        <SourceLinks />
      </div>
    </div>
  );
}
