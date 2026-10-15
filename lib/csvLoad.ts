// The published CSV of a layer is fetched once per page; rows are cut out in the browser (SPEC_WEB 0.2).
const csvCache = new Map<string, Promise<string>>();

export function loadCsv(url: string): Promise<string> {
  let p = csvCache.get(url);
  if (!p) {
    p = fetch(url).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.text();
    });
    p.catch(() => csvCache.delete(url));
    csvCache.set(url, p);
  }
  return p;
}
