// app/methodology/page.tsx
// Server Component — static content, no 'use client' needed
// Pattern B: manual JSX (no react-markdown dependency)
// Reason: avoids Tailwind prose class conflicts documented in SPEC §6.3,
// and ensures TypeScript strict mode compliance without extra dependency.

import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Methodology — The AI Buildout Frontier',
  description:
    'Grid Feasibility Index v1.0 methodology, Prince William County validation experiment, and roadmap to v2.0.',
};

export default function MethodologyPage() {
  return (
    <main className="min-h-screen bg-white">
      <div className="mx-auto max-w-[768px] px-6 py-10 md:px-12 md:py-14">

        {/* Back link */}
        <div className="mb-8">
          <Link
            href="/"
            className="text-sm text-slate-500 hover:text-slate-800 underline underline-offset-2"
          >
            ← Back to map
          </Link>
        </div>

        {/* Page title */}
        <h1 className="text-3xl font-semibold text-slate-900 mb-8 leading-tight">
          Methodology
        </h1>

        {/* ── Section 1: Grid Feasibility Index v1.0 ── */}
        <section>
          <h2 className="text-2xl font-semibold text-slate-900 mt-12 mb-4">
            Grid Feasibility Index v1.0
          </h2>

          <p className="text-base md:text-base leading-[1.7] text-slate-700 mb-4">
            The Grid Feasibility Index quantifies{' '}
            <strong className="font-semibold text-slate-800">
              structural pressure on regional electricity infrastructure
            </strong>{' '}
            from announced AI compute demand at sub-national resolution (L1-L2, counties,
        , districts, etc.). It is calculated for each region as:
          </p>

          {/* Formula block */}
          <div className="bg-slate-100 rounded p-4 mb-4 overflow-x-auto">
            <code className="font-mono text-sm text-slate-800 whitespace-nowrap">
              Feasibility = Available Capacity / Realistic Queue Pressure
            </code>
          </div>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            <strong className="font-semibold text-slate-800">Available Capacity</strong> ={' '}
            grid headroom (installed generation minus peak demand) + substation bonus
            (proximity to high-voltage critical-class substations) − transmission
            penalties (regional bottlenecks) − water penalties (in
            cooling-constrained regions). Headroom is sourced from EIA Form 861
            spatially joined to HIFLD utility service territories for U.S. counties;
            from Statistics Norway (SSB) Tables 08308 and 08313 for Norwegian fylker;
            and from IEA, IRENA, and GASTAT national totals disaggregated by
            population for Gulf regions.
          </p>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            <strong className="font-semibold text-slate-800">Realistic Queue Pressure</strong> ={' '}
            announced project capacity (MW) × (1 − historical completion rate). Queue
            data comes from Berkeley Lab&apos;s &ldquo;Queued Up 2024&rdquo;
            interconnection database for the United States, Statnett capacity
            reservations for Norway, and announced project pipelines from Global
            Energy Monitor for the Gulf. Historical completion rates differ by region:
            19.7% for PJM (U.S.), 40% for Norway, 55% for the Gulf, with an
            additional 30% geopolitical discount applied to UAE.
          </p>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            The output is mapped to five categories: low pressure (ratio ≥ 2.0),
            moderate pressure (1.0–2.0), high pressure (0.5–1.0), severe pressure
            (&lt; 0.5), plus a separate &ldquo;existing concentration&rdquo; overlay
            for regions where data center clusters are already established (Loudoun,
            Fairfax, Prince William, Arlington, and Oslo).
          </p>

          <p className="text-base leading-[1.7] text-slate-600 mb-4 border-l-4 border-slate-200 pl-4">
            <strong className="font-semibold text-slate-700">
              Important interpretive note.
            </strong>{' '}
            The index measures structural pressure, not project approval likelihood.
            High-pressure regions can and do see active construction. The score
            quantifies the cost of that construction — in rate increases for
            residential customers, multi-year power delivery delays, and risk of
            stranded transmission assets — not whether projects proceed.
          </p>
        </section>

        {/* ── Section 2: Validation Experiment ── */}
        <section>
          <h2 className="text-2xl font-semibold text-slate-900 mt-12 mb-4">
            Validation Experiment: Prince William County
          </h2>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            To test interpretation, we cross-referenced our Phase A index against
            actual under-construction data center projects in Prince William County
            (PWC), Northern Virginia, using the county&apos;s official interactive
            build-out dashboard.
          </p>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            PWC has a Grid Feasibility Index of{' '}
            <strong className="font-semibold text-slate-800">0.149</strong> — severe
            pressure category. The index reflects PWC&apos;s structural position: the
            county has negative net headroom (−481.8 MW), meaning it already imports
            electricity from neighboring regions through the PJM transmission network,
            while its interconnection queue contains 970 MW of new project capacity
            awaiting connection.
          </p>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            As of 2026,{' '}
            <strong className="font-semibold text-slate-800">
              31 data center buildings are listed as under construction in PWC
            </strong>
            .
          </p>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            This is not a contradiction. It is the central observation of the project.
          </p>

          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            Three independent data points tell one consistent story:
          </p>

          <ol className="list-decimal list-inside mb-4 space-y-2 text-base leading-[1.7] text-slate-700">
            <li>
              The Grid Feasibility Index identifies PWC as the highest-pressure region
              in Virginia.
            </li>
            <li>
              Dominion Energy itself acknowledges, in its 2024 Integrated Resource
              Plan, that contracted data center demand exceeds available transmission
              capacity by years; the utility constrains delivered load below contracted
              ESA amounts for periods of up to seven years.
            </li>
            <li>
              Virginia residential customers experienced electricity rate increases
              exceeding $11 per month in 2026, attributed by PJM&apos;s independent
              market monitor primarily to data center load growth.
            </li>
          </ol>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            The construction continues despite the structural deficit. The deficit is
            real. Both facts coexist because power delivery to a built data center is
            decoupled from the building&apos;s completion: developers race to break
            ground in anticipation of grid expansion that takes years to deliver. The
            result is exactly what the index describes — high structural pressure
            manifesting as externalities (rate increases, multi-year delays,
            transmission stress) rather than as project denials.
          </p>

          <p className="text-base leading-[1.7] text-slate-700 mb-4">
            The PWC validation confirms that the index is identifying the right
            phenomenon. It also reveals a known limitation: at county-level resolution,
            the index cannot distinguish between data centers connecting to substations
            with reserved capacity and those entering an indeterminate queue. Phase B
            addresses this through substation-level integration of HIFLD substation
            data and PJM interconnection queue data per substation.
          </p>
        </section>

        {/* ── Section 3: Roadmap ── */}
        <section>
          <h2 className="text-2xl font-semibold text-slate-900 mt-12 mb-4">
            Roadmap to v2.0
          </h2>

          <p className="text-base leading-[1.7] text-slate-700 mb-6">
            Three improvements are scheduled for Phase B (post-funding):
          </p>

          <div className="space-y-6">
            <div>
              <p className="text-base leading-[1.7] text-slate-700">
                <strong className="font-semibold text-slate-800">
                  Substation-level resolution.
                </strong>{' '}
                Replace county-level headroom estimates with substation-level capacity
                assessments using HIFLD substation classification (already prepared for
                Virginia, Norway, and Gulf regions) and PJM interconnection queue
                assignments to specific points of interconnection. This raises
                analytical resolution from ~3,000 km² (typical Virginia county) to
                ~5–50 km² (typical substation service area), capturing within-county
                heterogeneity that the current methodology cannot.
              </p>
            </div>

            <div>
              <p className="text-base leading-[1.7] text-slate-700">
                <strong className="font-semibold text-slate-800">
                  Time-separated validation.
                </strong>{' '}
                Use 2024 queue data to predict construction outcomes in 2025–2026
                across multiple U.S. states, scaling validation from one county to a
                regional dataset. This separates the prediction window from the input
                data window, addressing endogeneity concerns where current queue
                snapshots include projects already partially executed.
              </p>
            </div>

            <div>
              <p className="text-base leading-[1.7] text-slate-700">
                <strong className="font-semibold text-slate-800">
                  Cross-region methodology unification.
                </strong>{' '}
                Establish per-region versioning (v1.0-va, v1.0-no, v1.0-gulf)
                reflecting different completion rates, regulatory environments, and
                geopolitical risk discounts, with explicit transparency about how these
                regional adjustments affect comparability of scores across regions.
                Cross-region comparison is currently approximate; v2.0 will make the
                comparison explicit and methodologically defensible.
              </p>
            </div>
          </div>

          <p className="text-base leading-[1.7] text-slate-600 mt-8 mb-4">
            The methodology and underlying data are CC BY 4.0 licensed. Source code
            and data pipelines are available at{' '}
            <a
              href="https://github.com/Geofuturist/ai-buildout-frontier"
              className="underline underline-offset-2 hover:text-slate-800"
              target="_blank"
              rel="noopener noreferrer"
            >
              GitHub
            </a>
            . Detailed component breakdowns for each region are accessible through the
            interactive map by clicking on individual features.
          </p>
        </section>

        {/* ── Section: Datacenter sources ── */}
        <section>
          <h2 className="text-2xl font-semibold text-slate-900 mt-12 mb-4">
            Datacenter sources
          </h2>

          <p className="text-base leading-[1.7] text-slate-700 mb-6">
            Three independent datasets show where AI-relevant compute infrastructure
            exists, is being built, or is announced. Each is displayed as a separate
            toggleable layer on the map.
          </p>

          {/* Frontier */}
          <h3 className="text-lg font-semibold text-slate-900 mt-8 mb-3">
            Frontier AI Datacenters
          </h3>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Source:</strong>{' '}
            <a
              href="https://epoch.ai/data/frontier-data-centres"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline underline-offset-2 hover:text-blue-800"
            >
              Epoch AI Frontier Data Hub
            </a>{' '}
            (CC-BY-4.0).
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Coverage:</strong>{' '}
            38 datacenters globally, of which 33 have verified geographic coordinates.
            The remaining 5 are known to exist but lack precise location data and are
            excluded from the map.
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Methodology:</strong>{' '}
            Epoch AI identifies installations housing the largest training clusters by
            H100-equivalent compute. Coordinates are verified via satellite imagery
            where possible.
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-6">
            <strong className="font-semibold text-slate-800">Last updated:</strong>{' '}
            2026-05-04.
          </p>

          {/* GPU Clusters */}
          <h3 className="text-lg font-semibold text-slate-900 mt-8 mb-3">
            GPU Clusters
          </h3>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Source:</strong>{' '}
            <a
              href="https://epoch.ai/data/gpu-clusters"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline underline-offset-2 hover:text-blue-800"
            >
              Epoch AI GPU Clusters
            </a>{' '}
            (CC-BY-4.0).
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Coverage:</strong>{' '}
            786 clusters globally; 598 have coordinates and appear on the map. The
            remaining 188 are known to exist but lack precise location data.
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Methodology:</strong>{' '}
            Compiled from corporate disclosures, news reports, and regulatory filings.
            Each cluster carries a Certainty rating (Confirmed / Likely / Unlikely) and
            a Status field indicating lifecycle stage.
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-6">
            <strong className="font-semibold text-slate-800">Last updated:</strong>{' '}
            2026-05-04.
          </p>

          {/* OSM */}
          <h3 className="text-lg font-semibold text-slate-900 mt-8 mb-3">
            OpenStreetMap Datacenters (US)
          </h3>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Source:</strong>{' '}
            <a
              href="https://www.openstreetmap.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline underline-offset-2 hover:text-blue-800"
            >
              OpenStreetMap
            </a>{' '}
            (ODbL).
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-2">
            <strong className="font-semibold text-slate-800">Coverage:</strong>{' '}
            1,317 facilities tagged as datacenters in US OpenStreetMap. Currently US-only
            — global OSM coverage is uneven and would require additional curation.
          </p>
          <p className="text-base leading-[1.7] text-slate-700 mb-6">
            <strong className="font-semibold text-slate-800">Methodology:</strong>{' '}
            Community-maintained tags{' '}
            <code className="font-mono text-sm bg-slate-100 px-1 rounded">
              building=data_center
            </code>{' '}
            or{' '}
            <code className="font-mono text-sm bg-slate-100 px-1 rounded">
              man_made=data_center
            </code>
            . Includes all datacenter types, not only AI-relevant. Useful as broad
            infrastructure context against which specialized lists (Frontier, Clusters)
            can be compared.
          </p>

          {/* Notes */}
          <h3 className="text-lg font-semibold text-slate-900 mt-8 mb-3">
            Note on overlapping records
          </h3>
          <p className="text-base leading-[1.7] text-slate-700 mb-6">
            A single physical datacenter may appear in multiple datasets — for example,
            a large hyperscaler facility may be listed in the Epoch Frontier set, the
            GPU Clusters set, and OSM. We display each dataset independently rather than
            deduplicating, because each source applies different criteria for what counts
            as a "datacenter" and at what threshold. Researchers can compare and
            triangulate across layers.
          </p>

          <h3 className="text-lg font-semibold text-slate-900 mt-8 mb-3">
            Note on geocoding precision
          </h3>
          <p className="text-base leading-[1.7] text-slate-700 mb-6">
            Some sources report coordinates at varying precision: street-level (precise),
            city-level (centroid of municipality), regional (state/province centroid), or
            country-level (national centroid). We encode this visually as point opacity on
            the GPU Clusters layer once Epoch begins publishing precision metadata. As of
            the current data version, all coordinates render at default opacity (treated
            as city-level equivalent).
          </p>
        </section>

        {/* Document footer note */}
        <div className="mt-12 pt-6 border-t border-slate-200">
          <p className="text-sm text-slate-400 italic">
            Document version: 2026-04-25. Maintained by the AI Buildout Frontier
            project.
          </p>
        </div>

      </div>
    </main>
  );
}
