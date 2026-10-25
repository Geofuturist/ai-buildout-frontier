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
  coverage: { geography: string; iso3?: string | string[] | null; frame?: { iso3: string; level: string; country_name?: string } | null; n_units_frame: number | null; n_units_covered: number | null; n_records: number; known_gaps: string[] };
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
    /** breaks are the LOWER bounds of the classes (1, 10, 100, 1000 -> 1-9, 10-99, 100-999, 1000+) */
    breaks_fixed?: boolean;
    zero_class?: boolean;
    /** point layers: the field that sets the size, its thresholds and (for a class field) the classes in order */
    size_field?: string;
    size_breaks?: number[];
    size_classes?: string[];
    legend_title?: string;
    legend_note?: string;
    legend_zero?: string;
    legend_unknown?: string;
    legend_point?: string;
    /** false: the layer is not a map item (not drawn, not in the layers panel); files, /data and citation stay (abf-dc 0.2.0) */
    map?: boolean;
    /** point layers of places: from `count_breaks[0]` records the place is a badge with the number in this field, below it a point by size_field */
    count_field?: string;
    /** lower bounds of the badge classes, increasing (2, 10 -> 2-9 and 10+) */
    count_breaks?: number[];
  /** words the layer is found by in the search (besides its title, source, topic, scope and levels) */
  tags?: string[];
    /** operator type of the place (abf-dc 0.2.0): the field that sets the colour of a point and its classes in the legend order; the last class beyond the palette is grey */
    color_field?: string;
    color_classes?: string[];
    /** group -> the column that counts the records of that group in a place (n_type_<group>): the filter by type */
    filter_fields?: Record<string, string>;
    legend_type_title?: string;
    legend_type_note?: string;
    legend_type_labels?: Record<string, string>;
    legend_type_filter_all?: string;
    legend_layer_note?: string;
    legend_count_classes?: string[];
    list_title?: string;
    list_note?: string;
    /** caption of the fan of records (a schematic layout, not positions) */
    fan_note?: string;
    tile_fields?: string[];
    home_bbox?: [number, number, number, number];
    /** panel topic; absent in older metas (then derived from the domain) */
    topic?: string;
    series?: string;
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
  /** ISO3 the site opens on (content/site.json default_view.country), or null for the world */
  default_country: string | null;
  /** zoom at which the selection level changes to ADM1 / ADM2 (never below the boundary tiles minzoom) */
  level_zoom: { ADM1: number; ADM2: number };
  /** unit_type_en of boundary_registry.csv by country and level, e.g. { USA: { ADM1: 'state' } } */
  unit_words: Record<string, Record<string, string>>;
  /** every country of the boundaries (name from units.csv) with its box [w, s, e, n] (e may exceed 180), for the search */
  countries: { iso3: string; name: string; bbox: [number, number, number, number] | null }[];
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
