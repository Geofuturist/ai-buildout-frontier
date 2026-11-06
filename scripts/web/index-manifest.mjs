// Territory index in the manifests (SPEC_INDEX_territory r6 7): a manifest may carry `indexes`, one entry per index
// (index_id, of_dataset, of_version, layer_ids, meta{path,bytes,sha256}, country_files{path_pattern,count,listing},
// adm0_other, summary, archive). A dataset with kind "index" has no layers. Nothing here knows a dataset or country name.
// Pure: the caller hands in the readers, so the checks can be tested without a network.

/** true for a manifest that is allowed to have an empty list of layers */
export const isIndexManifest = (man) => man.kind === 'index';

/**
 * Reads the indexes of one manifest. Returns [{ id, dataset, version, base, country_url, adm0_other_url, license, meta }],
 * where `meta` is meta.json reduced to what the card needs (files reduced to country codes).
 */
export async function readIndexes(man, dsName, { getJson, sha256, strict, fail, fileUrl }) {
  const out = [];
  if (man.indexes === undefined) return out;
  if (!Array.isArray(man.indexes)) { fail(`${dsName}: indexes must be a list`); return out; }
  for (const ix of man.indexes) {
    const id = ix && ix.index_id;
    if (!id || !ix.meta || !ix.meta.path || !ix.meta.sha256 || !ix.country_files || !ix.country_files.path_pattern || !ix.adm0_other) {
      fail(`${dsName}: an entry of indexes lacks index_id, meta, country_files.path_pattern or adm0_other`);
      continue;
    }
    if (!/\{iso3\}/.test(ix.country_files.path_pattern)) fail(`${dsName}: ${id}: path_pattern has no {iso3}`);
    const { json: meta, bytes } = await getJson(man.base_path + ix.meta.path);
    const got = sha256(bytes);
    if (got !== ix.meta.sha256) strict(`${dsName}: ${id}: meta.json sha256 ${got.slice(0, 12)} differs from manifest ${ix.meta.sha256.slice(0, 12)}`);
    if (meta.schema_version !== 'abf-index-meta-1.0') fail(`${dsName}: ${id}: unexpected meta schema_version ${meta.schema_version}`);
    if (!meta.aggregations || !meta.layers || !meta.levels_by_country || !meta.files) fail(`${dsName}: ${id}: meta lacks aggregations, layers, levels_by_country or files`);
    const countries = Object.keys(meta.files).sort();
    if (ix.country_files.count != null && ix.country_files.count !== countries.length) strict(`${dsName}: ${id}: country_files.count ${ix.country_files.count} differs from meta (${countries.length})`);
    const license = man.license ?? meta.license ?? null;
    if (!license) strict(`${dsName}: ${id}: no license for the index (manifest or meta)`);
    out.push({
      id: meta.set ?? ix.of_dataset ?? id,
      index_id: id,
      dataset: dsName,
      version: man.version,
      index_version: meta.index_version ?? null,
      license,
      // {iso3} is replaced by the site; the set id (the file's own folder) is part of the pattern
      country_url: fileUrl(man.base_path, ix.country_files.path_pattern),
      adm0_other_url: fileUrl(man.base_path, ix.adm0_other.path),
      meta: {
        aggregations: meta.aggregations,
        levels_by_country: meta.levels_by_country,
        layers: meta.layers,
        countries,
        index_version: meta.index_version ?? '',
      },
    });
  }
  return out;
}
