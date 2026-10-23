// Build-time data fetch for the site (SPEC_WEB 2.1). Runs as `prebuild`.
//
//   node scripts/web/fetch-data.mjs
//
// Reads the pointer (manifest/latest.json for channel "final", manifest/dev.json for "dev"),
// both dataset manifests and every meta.json, checks them, and writes:
//   generated/abf-data.json   - everything the site reads (the site never reads the pointer at run time)
//   generated/methodology.md  - content/methodology.md with placeholders filled
//
// If anything is missing the build FAILS. There is no silent fallback to older data.
//
// Environment (all optional):
//   ABF_DATA_BASE_URL  default https://data.aibuildoutfrontier.org
//   ABF_CHANNEL        "final" | "dev". Default: final on Vercel Production, dev everywhere else
//   ABF_DATA_LOCAL     folder that mirrors the bucket layout (manifest/..., abf-layers/...) - development only
//   NEXT_PUBLIC_SITE_URL  used for the {domain} placeholder

import { createHash } from 'node:crypto';
import zlib from 'node:zlib';
import fs from 'node:fs';
import path from 'node:path';
import GithubSlugger from 'github-slugger';
import { featureBox } from './bbox.mjs';

const ROOT = process.cwd();
const BASE = (process.env.ABF_DATA_BASE_URL || 'https://data.aibuildoutfrontier.org').replace(/\/+$/, '');
const CHANNEL = process.env.ABF_CHANNEL || (process.env.VERCEL_ENV === 'production' ? 'final' : 'dev');
const LOCAL = process.env.ABF_DATA_LOCAL || '';
const STRICT = CHANNEL === 'final';
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://aibuildoutfrontier.org';
const ARCHIVE_V1_URL =
  'https://github.com/Geofuturist/ai-buildout-frontier/blob/gfi-v1.0/app/methodology/page.tsx';
const DOI_RE = /^10\.5281\/zenodo\.\d+$/;

const warnings = [];

function fail(msg) {
  console.error(`\nFETCH-DATA STOP: ${msg}\n`);
  process.exit(1);
}

/** Problem that stops the build in channel "final" and is only a warning in "dev". */
function strict(msg) {
  if (STRICT) fail(msg);
  warnings.push(msg);
  console.warn(`WARN (dev channel): ${msg}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Returns the bytes of a file of the data bucket (network or ABF_DATA_LOCAL). */
async function getBytes(rel, { bust = false } = {}) {
  if (LOCAL) {
    const p = path.join(LOCAL, rel);
    if (!fs.existsSync(p)) fail(`local file not found: ${p}`);
    return fs.readFileSync(p);
  }
  const url = `${BASE}/${rel}${bust ? `?t=${Date.now()}` : ''}`;
  let lastErr = '';
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      const res = await fetch(url, { headers: { 'cache-control': 'no-cache' } });
      if (res.ok) return Buffer.from(await res.arrayBuffer());
      lastErr = `HTTP ${res.status}`;
      if (res.status === 404) break; // retrying will not help
    } catch (e) {
      lastErr = String(e && e.message ? e.message : e);
    }
    await sleep(1500 * attempt);
  }
  fail(`could not download ${url} (${lastErr})`);
  return Buffer.alloc(0);
}

async function getJson(rel, opts) {
  const bytes = await getBytes(rel, opts);
  try {
    return { json: JSON.parse(bytes.toString('utf8')), bytes };
  } catch {
    fail(`${rel} is not valid JSON`);
  }
  return { json: null, bytes };
}

const sha256 = (b) => createHash('sha256').update(b).digest('hex');
const fileUrl = (basePath, p) => `${BASE}/${basePath}${p}`;
const withUrl = (basePath, f) => ({ path: f.path, bytes: f.bytes, sha256: f.sha256, url: fileUrl(basePath, f.path), description: f.description });

function longDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  if (!m) return iso || '';
  const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  return `${Number(m[3])} ${months[Number(m[2]) - 1]} ${m[1]}`;
}

async function main() {
  console.log(`fetch-data: channel=${CHANNEL} ${LOCAL ? `local=${LOCAL}` : `base=${BASE}`}`);

  // 1. Pointer
  const pointerPath = STRICT ? 'manifest/latest.json' : 'manifest/dev.json';
  const { json: pointer } = await getJson(pointerPath, { bust: true });
  if (pointer.schema_version !== 'abf-latest-1.0') fail(`${pointerPath}: unexpected schema_version ${pointer.schema_version}`);
  // Every dataset of the pointer is read; no dataset name is known in advance (ADR 4.4)
  const dsNames = Object.keys(pointer.datasets || {});
  if (dsNames.length === 0) fail(`${pointerPath} lists no datasets`);
  for (const n of dsNames) if (!/^abf-[a-z0-9]+$/.test(n)) fail(`${pointerPath}: unexpected dataset name "${n}"`);

  const datasets = {};
  const layers = [];
  const metas = {};

  // 2. Manifests and metas
  for (const dsName of dsNames) {
    const ptr = pointer.datasets[dsName];
    const { json: man } = await getJson(ptr.manifest);
    if (man.schema_version !== 'abf-manifest-1.0') fail(`${ptr.manifest}: unexpected schema_version`);
    if (man.dataset !== dsName) fail(`${ptr.manifest}: dataset is ${man.dataset}, expected ${dsName}`);
    if (man.version !== ptr.version) fail(`${ptr.manifest}: version ${man.version} differs from pointer ${ptr.version}`);
    if (!man.base_path || !Array.isArray(man.layers) || man.layers.length === 0) fail(`${ptr.manifest}: base_path or layers missing`);
    if (man.doi == null) strict(`${dsName} ${man.version}: DOI is null`);
    else if (!DOI_RE.test(man.doi)) fail(`${dsName}: DOI "${man.doi}" does not look like 10.5281/zenodo.N`);

    datasets[dsName] = {
      dataset: man.dataset,
      version: man.version,
      tag: man.tag,
      doi: man.doi ?? null,
      published_at: man.published_at,
      base_path: man.base_path,
      boundary_release: man.boundary_release ?? null,
      extra_files: (man.extra_files || []).map((f) => withUrl(man.base_path, f)),
      source_archives: (man.source_archives || []).map((f) => withUrl(man.base_path, f)),
    };

    const metaCache = new Map();
    for (const l of man.layers) {
      // meta.json (several boundary entries share one)
      const metaRel = man.base_path + l.meta.path;
      let meta = metaCache.get(metaRel);
      if (!meta) {
        const { json, bytes } = await getJson(metaRel);
        const got = sha256(bytes);
        if (got !== l.meta.sha256) strict(`${metaRel}: sha256 ${got.slice(0, 12)} differs from manifest ${l.meta.sha256.slice(0, 12)}`);
        meta = json;
        metaCache.set(metaRel, meta);
        if (meta.schema_version !== 'abf-meta-1.0') fail(`${metaRel}: unexpected schema_version`);
        if (!meta.layer_id || !meta.license || !Array.isArray(meta.sources) || meta.sources.length === 0) fail(`${metaRel}: layer_id, license or sources missing`);
        if (meta.kind === 'layer' && meta.layer_id !== l.layer_id) fail(`${metaRel}: layer_id ${meta.layer_id} differs from manifest ${l.layer_id}`);
        if (meta.release && meta.release.doi !== man.doi) fail(`${metaRel}: release.doi differs from manifest DOI`);
        if (metas[meta.layer_id]) fail(`duplicate meta layer_id ${meta.layer_id}`);
        metas[meta.layer_id] = meta;
      }
      const files = {};
      for (const [fmt, f] of Object.entries(l.files || {})) files[fmt] = withUrl(man.base_path, f);
      if (!files.parquet || !files['geojson.gz']) fail(`${l.layer_id}: parquet or geojson.gz missing in manifest`);
      if (meta.kind === 'layer' && !files.csv) fail(`${l.layer_id}: csv missing in manifest`);
      if (!l.tiles || !l.tiles.file) fail(`${l.layer_id}: no tiles entry`);
      layers.push({
        dataset: dsName,
        layer_id: l.layer_id,
        meta_id: meta.layer_id,
        title: l.title,
        domain: l.domain,
        level: l.level,
        bbox: l.bbox ?? null,
        files,
        extra_files: (l.extra_files || []).map((f) => withUrl(man.base_path, f)),
        tiles: {
          url: fileUrl(man.base_path, l.tiles.file),
          source_layer: l.tiles.source_layer,
          geometry_type: l.tiles.geometry_type,
          minzoom: l.tiles.minzoom,
          maxzoom: l.tiles.maxzoom,
          fields: l.tiles.fields,
        },
      });
    }
    // A dataset is "boundaries" when its metadata say kind = boundaries (never by name)
    const kinds = new Set([...metaCache.values()].map((m) => m.kind));
    if (kinds.size !== 1) fail(`${dsName}: mixes metadata kinds (${[...kinds].join(', ')})`);
    datasets[dsName].kind = kinds.has('boundaries') ? 'boundaries' : 'layers';
  }

  const boundaryNames = dsNames.filter((n) => datasets[n].kind === 'boundaries');
  if (boundaryNames.length !== 1) fail(`expected exactly one boundaries dataset, found ${boundaryNames.length}`);
  const bnd = datasets[boundaryNames[0]];
  const layerNames = dsNames.filter((n) => datasets[n].kind === 'layers');
  if (layerNames.length === 0) fail('no dataset of layers in the pointer');

  // boundary_release (SPEC_META 6 p.25): a dataset may refer to a boundaries version that is not newer than the
  // current one (boundaries are only ever extended). Checking that every unit_id exists in the boundaries is a
  // publishing gate (G4); the site has no access to the ids at build time.
  const semver = (v) => v.split('.').map(Number);
  const newer = (a, b) => { const x = semver(a), y = semver(b); for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i]; return false; };
  for (const n of layerNames) {
    const m = new RegExp(`^${bnd.dataset}-v(\\d+\\.\\d+\\.\\d+)$`).exec(datasets[n].boundary_release || '');
    if (!m) strict(`${n}: boundary_release "${datasets[n].boundary_release}" is not a ${bnd.dataset} version`);
    else if (newer(m[1], bnd.version)) strict(`${n} refers to boundaries v${m[1]}, newer than the current v${bnd.version}`);
  }

  // content/site.json: default_layer (the indicator that is on when a country is chosen), default_view.country
  // (a country the site opens on, or null for the world) and level_zoom (zoom thresholds of ADM1 / ADM2, SPEC_WEB_territory 4).
  // Pointer order is alphabetical, so "the first layer" would depend on dataset names.
  let defaultLayer = null;
  let defaultCountry = null;
  let site = {};
  const sitePath = path.join(ROOT, 'content', 'site.json');
  if (fs.existsSync(sitePath)) {
    try {
      site = JSON.parse(fs.readFileSync(sitePath, 'utf8'));
    } catch {
      fail('content/site.json is not valid JSON');
    }
    if (site.default_layer) {
      if (layers.some((l) => l.layer_id === site.default_layer && datasets[l.dataset].kind === 'layers')) defaultLayer = site.default_layer;
      else strict(`content/site.json: default_layer "${site.default_layer}" is not a layer of the pointer; the first fill layer is used`);
    }
    const dc = site.default_view && site.default_view.country;
    if (dc) {
      if (/^[A-Z]{3}$/.test(dc)) defaultCountry = dc;
      else strict(`content/site.json: default_view.country "${dc}" is not an ISO3 code; the site opens on the world`);
    }
  }

  // Zoom thresholds: never below the minzoom of the boundary tiles of that level (below it the tiles hold no units).
  const levelZoom = {};
  for (const lvl of ['ADM1', 'ADM2']) {
    const tiles = layers.find((l) => l.dataset === bnd.dataset && l.level === lvl);
    const minz = tiles ? tiles.tiles.minzoom : 0;
    const wanted = site.level_zoom && typeof site.level_zoom[lvl] === 'number' ? site.level_zoom[lvl] : lvl === 'ADM1' ? 3.0 : 5.5;
    if (wanted < minz) {
      const msg = `content/site.json: level_zoom.${lvl} = ${wanted} is below the boundary tiles minzoom ${minz}; raised to ${minz}`;
      warnings.push(msg);
      console.warn(`WARN: ${msg}`);
    }
    levelZoom[lvl] = Math.max(wanted, minz);
  }

  // Territory (SPEC_WEB_territory 5, 10): units of the countries that have layers, from units.csv of the boundaries
  // dataset (never from geometry), and the unit words of boundary_registry.csv. units.csv goes to a lazily loaded
  // file (territory.json); the registry words and thresholds travel with abf-data.json.
  const csvRows = (text) => {
    const out = [];
    let row = [], cur = '', q = false;
    const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
    for (let i = 0; i < src.length; i++) {
      const c = src[i];
      if (q) { if (c === '"') { if (src[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += c; }
      else if (c === '"') q = true;
      else if (c === ',') { row.push(cur); cur = ''; }
      else if (c === '\n' || c === '\r') { if (c === '\r' && src[i + 1] === '\n') i++; row.push(cur); if (row.length > 1 || row[0] !== '') out.push(row); row = []; cur = ''; }
      else cur += c;
    }
    if (cur !== '' || row.length) { row.push(cur); out.push(row); }
    const head = out.shift() || [];
    return out.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
  };
  const bndFile = async (name) => {
    const f = bnd.extra_files.find((x) => x.path === name);
    if (!f) { strict(`${bnd.dataset}: extra file ${name} is not in the manifest`); return null; }
    const bytes = await getBytes(bnd.base_path + f.path);
    const got = sha256(bytes);
    if (got !== f.sha256) strict(`${f.path}: sha256 ${got.slice(0, 12)} differs from manifest ${f.sha256.slice(0, 12)}`);
    return bytes.toString('utf8');
  };
  const unitsText = await bndFile('units.csv');
  const registryText = await bndFile('boundary_registry.csv');
  const countryCodes = new Set();
  for (const m of Object.values(metas)) {
    if (m.kind !== 'layer') continue;
    const c = (Array.isArray(m.coverage.iso3) ? m.coverage.iso3[0] : m.coverage.iso3) || (m.coverage.frame && m.coverage.frame.iso3);
    if (c) countryCodes.add(c);
  }
  const territory = { units: {} };
  if (unitsText) {
    const LEVEL = { ADM0: 0, ADM1: 1, ADM2: 2 };
    for (const r of csvRows(unitsText)) {
      if (!countryCodes.has(r.iso3) || !(r.level in LEVEL)) continue;
      // unit_id -> [level, name, parent_id]
      territory.units[r.unit_id] = [LEVEL[r.level], r.name, r.parent_id];
    }
    if (Object.keys(territory.units).length === 0) strict('units.csv holds no units of the countries that have layers');
  }
  const unitWords = {};
  if (registryText) {
    for (const r of csvRows(registryText)) {
      if (!r.iso3 || !r.level || !r.unit_type_en) continue;
      (unitWords[r.iso3] = unitWords[r.iso3] || {})[r.level] = r.unit_type_en;
    }
  }

  // Countries for the search by name: every ADM0 unit of units.csv (name) with a box from the ADM0 geometry
  // (boundaries geojson.gz, read here once; antimeridian handled in bbox.mjs).
  const countries = [];
  if (unitsText) {
    const adm0 = layers.find((l) => l.dataset === bnd.dataset && l.tiles.source_layer === 'adm0');
    const boxes = {};
    const gj = adm0 && adm0.files['geojson.gz'];
    if (gj) {
      try {
        const bytes = await getBytes(bnd.base_path + gj.path);
        const fc = JSON.parse(zlib.gunzipSync(bytes).toString('utf8'));
        for (const f of fc.features || []) {
          const id = f.properties && (f.properties.unit_id || f.properties.iso3);
          const b = id ? featureBox(f.geometry) : null;
          if (b) boxes[id] = b;
        }
      } catch (e) {
        strict(`country boxes: could not read the ADM0 geometry (${e && e.message ? e.message : e})`);
      }
    } else strict('country boxes: the ADM0 layer has no geojson.gz in the manifest');
    for (const r of csvRows(unitsText)) {
      if (r.level !== 'ADM0') continue;
      countries.push({ iso3: r.unit_id, name: r.name, bbox: boxes[r.unit_id] || null });
    }
    countries.sort((a, b) => a.name.localeCompare(b.name, 'en'));
    const missing = countries.filter((c) => !c.bbox).length;
    if (missing) {
      const msg = `${missing} of ${countries.length} countries have no box (the search selects them without flying)`;
      warnings.push(msg);
      console.warn(`WARN: ${msg}`);
    }
  }

  // 3. Methodology placeholders and anchors
  const layerTitles = layers.filter((l) => datasets[l.dataset].kind === 'layers').map((l) => ({ id: l.layer_id, title: l.title }));
  const mdSrc = fs.readFileSync(path.join(ROOT, 'content', 'methodology.md'), 'utf8');
  const doiLink = (d) => (d.doi ? `[${d.doi}](https://doi.org/${d.doi})` : 'not assigned yet');
  const primary = (id) => {
    const m = metas[id];
    return m ? (m.sources.find((s) => s.role === 'primary') || m.sources[0]) : null;
  };
  let unfilled = 0;
  const md = mdSrc.replace(
    /\{(DOI_layers|DOI_boundaries|version_layers|version_boundaries|release_date(?::abf-[a-z0-9]+)?|domain|archive_v1_url|(?:DOI|version):abf-[a-z0-9]+|(?:edition|current_through):[a-z0-9_]+)\}/g,
    (token, name) => {
      // Old names are synonyms: {DOI_layers} = {DOI:abf-layers}, {DOI_boundaries} = {DOI:<boundaries dataset>}, ...
      const named = (id) => {
        const d = datasets[id];
        if (!d) { unfilled++; strict(`methodology: ${token} - no dataset ${id} in the pointer`); }
        return d;
      };
      const syn = { DOI_layers: ['DOI', 'abf-layers'], version_layers: ['version', 'abf-layers'], release_date: ['release_date', 'abf-layers'],
                    DOI_boundaries: ['DOI', bnd.dataset], version_boundaries: ['version', bnd.dataset] };
      let kind, id;
      if (syn[name]) [kind, id] = syn[name];
      else if (/^(DOI|version|release_date):/.test(name)) [kind, id] = name.split(':');
      if (kind) {
        const d = named(id);
        if (!d) return token;
        if (kind === 'DOI') return doiLink(d);
        if (kind === 'version') return d.version;
        return longDate(d.published_at);
      }
      switch (name) {
        case 'domain': return new URL(SITE_URL).host;
        case 'archive_v1_url': return ARCHIVE_V1_URL;
        default: {
          const [k2, lid] = name.split(':');
          const m = metas[lid];
          if (!m) { unfilled++; strict(`methodology: ${token} - no layer ${lid}`); return token; }
          if (k2 === 'edition') return primary(lid).edition;
          return m.freshness.source_current_through;
        }
      }
    },
  );
  if (unfilled) console.warn(`methodology: ${unfilled} placeholder(s) left unfilled`);

  // Anchors: slug(title) must be a heading of the methodology (same algorithm as rehype-slug)
  const slugger = new GithubSlugger();
  const headingSlugs = new Map();
  let inFence = false;
  for (const line of md.split('\n')) {
    if (/^```/.test(line)) inFence = !inFence;
    if (inFence) continue;
    const h = /^#{1,6}\s+(.+?)\s*#*$/.exec(line);
    if (!h) continue;
    const text = h[1].replace(/[*_`]/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
    headingSlugs.set(slugger.slug(text), text);
  }
  const anchors = {};
  for (const lt of layerTitles) {
    const s = new GithubSlugger().slug(lt.title);
    anchors[lt.id] = s;
    if (!headingSlugs.has(s)) strict(`methodology has no heading for layer "${lt.title}" (expected anchor #${s})`);
  }

  // 4. Attribution (from sources[] of every meta.json), grouped by license family
  const bySource = new Map();
  for (const m of Object.values(metas)) {
    for (const s of m.sources) {
      const prev = bySource.get(s.source_id);
      if (prev) {
        if (prev.license.id !== s.license.id) fail(`source ${s.source_id} has two different licenses (${prev.license.id} / ${s.license.id})`);
        if (!prev.layers.includes(m.title)) prev.layers.push(m.title);
      } else {
        bySource.set(s.source_id, {
          source_id: s.source_id,
          role: s.role,
          publisher: s.publisher,
          product: s.product,
          url: s.url,
          edition: s.edition,
          current_through: s.current_through,
          license: s.license,
          rights_basis_text: s.rights_basis ? s.rights_basis.text : '',
          publication_mode: s.publication_mode,
          layers: [m.title],
        });
      }
    }
  }
  const families = ['public_domain', 'attribution', 'share_alike'];
  const groups = families
    .map((family) => ({
      family,
      sources: [...bySource.values()].filter((s) => s.license.family === family).sort((a, b) => a.publisher.localeCompare(b.publisher)),
    }))
    .filter((g) => g.sources.length > 0);
  const other = [...bySource.values()].filter((s) => !families.includes(s.license.family));
  if (other.length) fail(`sources with license family outside ${families.join('/')}: ${other.map((s) => s.source_id).join(', ')}`);
  const shown = groups.reduce((n, g) => n + g.sources.length, 0);
  const uniqueIds = new Set(Object.values(metas).flatMap((m) => m.sources.map((s) => s.source_id))).size;
  if (shown !== uniqueIds) fail(`attribution page would show ${shown} sources, metadata has ${uniqueIds}`);

  // 5. Write
  const out = {
    generated_at: new Date().toISOString(),
    channel: CHANNEL,
    base_url: BASE,
    site_url: SITE_URL,
    pointer_updated_at: pointer.updated_at,
    datasets,
    layers,
    metas,
    anchors,
    default_layer: defaultLayer,
    default_country: defaultCountry,
    level_zoom: levelZoom,
    unit_words: unitWords,
    countries,
    attribution: groups,
    warnings,
  };
  fs.mkdirSync(path.join(ROOT, 'generated'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'generated', 'abf-data.json'), JSON.stringify(out));
  fs.writeFileSync(path.join(ROOT, 'generated', 'methodology.md'), md);
  fs.writeFileSync(path.join(ROOT, 'generated', 'territory.json'), JSON.stringify(territory));
  console.log(
    `fetch-data: ok. ${dsNames.map((n) => `${n} v${datasets[n].version} (${layers.filter((l) => l.dataset === n).length} entries)`).join(', ')}; ` +
      `${shown} sources, ${warnings.length} warning(s)`,
  );
}

main().catch((e) => fail(String(e && e.stack ? e.stack : e)));
