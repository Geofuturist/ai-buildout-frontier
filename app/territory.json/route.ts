// Units of the countries that have layers (from units.csv of the boundaries dataset), written by fetch-data.
// Loaded by the map on the first choice of a territory; not part of the page (SPEC_WEB_territory 10).
import fs from 'node:fs';
import path from 'node:path';

export const dynamic = 'force-static';

export function GET() {
  const body = fs.readFileSync(path.join(process.cwd(), 'generated', 'territory.json'), 'utf8');
  return new Response(body, { headers: { 'content-type': 'application/json; charset=utf-8' } });
}
