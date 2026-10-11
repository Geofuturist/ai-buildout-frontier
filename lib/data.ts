// Types for generated/abf-data.json (written by scripts/web/fetch-data.mjs at build time) and the loaders.
// Server-side only (reads the file during the static build).
import fs from 'node:fs';
import path from 'node:path';

export interface FileRef {
  path: string;
  bytes: number;
  sha256: string;
  url: string;
  description?: string;
}

export interface LicenseInfo {
  id: string;
  name: string;
  url: string;
  family: 'public_domain' | 'attribution' | 'share_alike';
  attribution_text: string;
}

export interface FieldDef {
  name: string;
  type: string;
  unit?: string;
  nullable?: boolean;
  description?: string;
  null_meaning?: { not_covered?: string | null; covered?: string | null } | string | null;
}

export interface SourceInfo {
  source_id: string;
  role: string;
  publisher: string;
  product: string;
  url: string;
  edition: string;
  current_through: string | null;
  license: LicenseInfo;
}

export interface Meta {
  schema_version: string;
  kind: 'layer' | 'boundaries';
  layer_id: string;
  title: string;
  title_ru?: string;
  description: string;
  level?: string;
  levels?: string[];
  fields: FieldDef[];
  sources: SourceInfo[];
  license: LicenseInfo;
  freshness: { source_current_through: string | null; source_cadence: string; built_at: string; next_check: string | null };
  coverage: { geography: string; iso3?: string | null; frame?: { iso3: string; level: string; country_name?: string } | null; n_units_frame: number | null; n_units_covered: number | null; n_records: number; known_gaps: string[] };
  release: { dataset: string; version: string; tag: string; doi: string | null; published_at: string };
  verification: {
    levels: Record<string, number>;
    method: string;
    sample_share: Record<string, number>;
    automated_checks: { id: string; description: string }[];
  };
  citation: { text: string; record_pattern: string };
  display?: {
    geometry_type?: string;
    value_field?: string;
    unit?: string;
    breaks?: number[];
    zero_class?: boolean;
    legend_title?: string;
    tile_fields?: string[];
    home_bbox?: [number, number, number, number];
  };
}

export interface LayerEntry {
  dataset: string;
  layer_id: string;
  meta_id: string;
  title: string;
  domain: string;
  level: string;
  bbox: [number, number, number, number] | null;
  files: Record<string, FileRef>;
  extra_files: FileRef[];
  tiles: {
    url: string;
    source_layer: string;
    geometry_type: 'polygon' | 'line' | 'point';
    minzoom: number;
    maxzoom: number;
    fields: string[];
  };
}

export interface DatasetInfo {
  dataset: string;
  /** 'boundaries' when the metadata of the dataset have kind = boundaries, otherwise 'layers' */
  kind: 'boundaries' | 'layers';
  version: string;
  tag: string;
  doi: string | null;
  published_at: string;
  base_path: string;
  boundary_release: string | null;
  extra_files: FileRef[];
  source_archives: FileRef[];
}

export interface AttributionSource {
  source_id: string;
  role: string;
  publisher: string;
  product: string;
  url: string;
  edition: string;
  current_through: string | null;
  license: LicenseInfo;
  rights_basis_text: string;
  publication_mode: string;
  layers: string[];
}

export interface AbfData {
  generated_at: string;
  channel: 'final' | 'dev';
  base_url: string;
  site_url: string;
  /** every dataset of the pointer, in pointer order */
  datasets: Record<string, DatasetInfo>;
  layers: LayerEntry[];
  metas: Record<string, Meta>;
  anchors: Record<string, string>;
  /** layer_id that is on when the map opens (content/site.json), or null */
  default_layer: string | null;
  attribution: { family: LicenseInfo['family']; sources: AttributionSource[] }[];
  warnings: string[];
}

let cache: AbfData | null = null;

export function getData(): AbfData {
  if (!cache) {
    const p = path.join(process.cwd(), 'generated', 'abf-data.json');
    if (!fs.existsSync(p)) throw new Error('generated/abf-data.json is missing: run "npm run fetch-data" (it runs automatically in "npm run build").');
    cache = JSON.parse(fs.readFileSync(p, 'utf8')) as AbfData;
  }
  return cache;
}

export function getMethodology(): string {
  return fs.readFileSync(path.join(process.cwd(), 'generated', 'methodology.md'), 'utf8');
}
