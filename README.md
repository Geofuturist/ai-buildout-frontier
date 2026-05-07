# The AI Buildout Frontier

Public tracker of physical constraints on AI infrastructure buildout — compute, energy, geopolitics.

**Live:** https://ai-buildout-frontier.vercel.app

---

## About

This project maps the physical bottlenecks constraining AI infrastructure growth: electricity grid topology, substation capacity, and queue pressure from announced datacenters.

**Central hypothesis:** _Announced AI capacity ≠ physically deliverable AI capacity._

The standard metric — installed generation capacity — captures only the first link in a chain. Substations, transmission corridors, water infrastructure, and political stability are not background conditions. They are the chain itself.

**Current scope:** Virginia pilot (133 counties + independent cities), Grid Feasibility Index v1.0.

The **Grid Feasibility Index** contrasts raw headroom with realistic queue pressure:

```
Feasibility Ratio = Available Capacity (MW) / Realistic Queue Pressure (MW)
```

| Category | Ratio | Colour |
|---|---|---|
| High feasibility | ≥ 2.0 | Green |
| Moderate feasibility | 1.0–2.0 | Yellow |
| Low feasibility | 0.5–1.0 | Orange |
| Critical constraint | < 0.5 | Red |
| DC Hotspot (override) | — | Dark red |

## Features

- County-level grid feasibility scores (Virginia pilot, 133 counties)
- Datacenter layers:
  - Frontier AI Datacenters (Epoch AI, 38 records, 33 spatial)
  - GPU Clusters (Epoch AI, 786 records, 598 spatial)
  - OpenStreetMap datacenters (US, 1,317 records)
- Interactive layer toggles with status sub-filters (planned / decommissioned)
- Shareable URL state for filtered views
- Cluster aggregation on zoom-out for Clusters and OSM layers
- Methodology and data source documentation

## Data sources

**Grid feasibility:**
- **EIA Form 861** — net generation and retail service territories, joined to HIFLD boundaries
- **Berkeley Lab LBNL Interconnection Queue Data** — generation queue projects by county (PJM, historical completion rate 19.7%)
- **OpenStreetMap via Overpass API** — substation locations and voltage classification
- **US Census TIGER** — county and independent city boundaries

**Datacenter layers:**
- **Frontier datacenters:** [Epoch AI Frontier Data Hub](https://epoch.ai/data/frontier-data-centres) (CC-BY-4.0)
- **GPU clusters:** [Epoch AI GPU Clusters](https://epoch.ai/data/gpu-clusters) (CC-BY-4.0)
- **OSM datacenters:** [OpenStreetMap](https://www.openstreetmap.org/) (ODbL)

Full methodology: see [methodology page](https://project-j8oo5.vercel.app/methodology) or `app/methodology/page.tsx`.

## Local development

**Requirements:** Node.js 20 LTS, npm

```bash
# 1. Clone the repo
git clone https://github.com/Geofuturist/ai-buildout-frontier.git
cd ai-buildout-frontier

# 2. Install dependencies
npm install

# 3. Create your local environment file
cp .env.example .env.local
# Then edit .env.local — add your Supabase URL and publishable key

# 4. Start the dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Environment variables

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Publishable (read-only) key — safe for browser |

⚠️ Never use the Supabase **secret** key in the frontend.

## Deployment (Vercel)

1. Push your code to `main` on GitHub
2. Go to [vercel.com](https://vercel.com) → Sign in with GitHub
3. **New Project** → Import `ai-buildout-frontier`
4. Framework preset: **Next.js** (auto-detected)
5. Add Environment Variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
6. Click **Deploy**

Every push to `main` triggers an automatic redeploy.

## Tech stack

| Layer | Tool |
|---|---|
| Frontend | Next.js 14 (App Router) + React 18 |
| Map | MapLibre GL JS |
| Database | Supabase (PostgreSQL + PostGIS) |
| Styling | Tailwind CSS |
| Deployment | Vercel |

## Project structure

```
app/
  components/
    AppShell.tsx      # Client layout shell (sidebar + map area + mobile sheet)
    Header.tsx        # Top navigation bar
    Map.tsx           # MapLibre map — county + 3 DC layers (client component)
    Legend.tsx        # Feasibility category legend
    LayerPanel.tsx    # Layer toggle controls
    BottomSheet.tsx   # Mobile slide-up panel
    DCPopup.tsx       # Datacenter popup (3 variants)
  methodology/
    page.tsx          # Methodology documentation
  layout.tsx          # Root layout
  page.tsx            # Homepage (server component — data fetching)
  globals.css
lib/
  supabase.ts         # Supabase client singleton
  feasibility.ts      # Types, color mapping, helpers
  queries/
    datacenters.ts    # DC fetch functions (Frontier, Clusters, OSM)
  hooks/
    useLayerState.ts  # URL-backed layer toggle state
```

## License

[CC BY 4.0](LICENSE) — use freely with attribution.

## Author

Volodymyr Ilin — geographer, AI infrastructure researcher.  
[Substack](https://substack.com/@volodymyrilin) | Research: compute geopolitics, middle AI powers, AI energy constraints
