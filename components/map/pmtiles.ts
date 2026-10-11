// Registers the pmtiles:// protocol once per page load (guards against hot-reload double registration).
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';

const FLAG = '__abfPmtilesRegistered';

export function registerPmtiles(): void {
  const g = globalThis as unknown as Record<string, unknown>;
  if (g[FLAG]) return;
  g[FLAG] = true;
  const protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
}
