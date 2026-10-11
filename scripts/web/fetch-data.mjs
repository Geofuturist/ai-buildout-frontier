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
import fs from 'node:fs';
import path from 'node:path';
import GithubSlugger from 'github-slugger';

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
  for (const ds of ['abf-layers', 'abf-boundaries']) {
    if (!pointer.datasets || !pointer.datasets[ds]) fail(`${pointerPath} has no dataset ${ds}`);
  }

  const datasets = {};
  const layers = [];
  const metas = {};

  // 2. Manifests and metas
  for (const dsName of ['abf-layers', 'abf-boundaries']) {
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
  }

  if (datasets['abf-layers'].boundary_release !== `abf-boundaries-v${datasets['abf-boundaries'].version}`) {
    strict(`abf-layers points to ${datasets['abf-layers'].boundary_release}, but the boundaries dataset is v${datasets['abf-boundaries'].version}`);
  }

  // 3. Methodology placeholders and anchors
  const layerTitles = layers.filter((l) => l.dataset === 'abf-layers').map((l) => ({ id: l.layer_id, title: l.title }));
  const mdSrc = fs.readFileSync(path.join(ROOT, 'content', 'methodology.md'), 'utf8');
  const lay = datasets['abf-layers'];
  const bnd = datasets['abf-boundaries'];
  const doiLink = (d) => (d.doi ? `[${d.doi}](https://doi.org/${d.doi})` : 'not assigned yet');
  const primary = (id) => {
    const m = metas[id];
    return m ? (m.sources.find((s) => s.role === 'primary') || m.sources[0]) : null;
  };
  let unfilled = 0;
  const md = mdSrc.replace(
    /\{(DOI_layers|DOI_boundaries|version_layers|version_boundaries|release_date|domain|archive_v1_url|(?:edition|current_through):[a-z0-9_]+)\}/g,
    (token, name) => {
      switch (name) {
        case 'DOI_layers': return doiLink(lay);
        case 'DOI_boundaries': return doiLink(bnd);
        case 'version_layers': return lay.version;
        case 'version_boundaries': return bnd.version;
        case 'release_date': return longDate(lay.published_at);
        case 'domain': return new URL(SITE_URL).host;
        case 'archive_v1_url': return ARCHIVE_V1_URL;
        default: {
          const [kind, id] = name.split(':');
          const m = metas[id];
          if (!m) { unfilled++; strict(`methodology: ${token} - no layer ${id}`); return token; }
          if (kind === 'edition') return primary(id).edition;
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
    attribution: groups,
    warnings,
  };
  fs.mkdirSync(path.join(ROOT, 'generated'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'generated', 'abf-data.json'), JSON.stringify(out));
  fs.writeFileSync(path.join(ROOT, 'generated', 'methodology.md'), md);
  console.log(
    `fetch-data: ok. layers v${lay.version} (${layers.filter((l) => l.dataset === 'abf-layers').length} layers), ` +
      `boundaries v${bnd.version}, ${shown} sources, ${warnings.length} warning(s)`,
  );
}

main().catch((e) => fail(String(e && e.stack ? e.stack : e)));
