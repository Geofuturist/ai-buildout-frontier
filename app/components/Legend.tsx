import { FEASIBILITY_COLORS, FEASIBILITY_LABELS, type FeasibilityCategory } from '@/lib/feasibility';

const CATEGORIES: FeasibilityCategory[] = [
  'high_feasibility',
  'moderate_feasibility',
  'low_feasibility',
  'critical_constraint',
  'dc_hotspot',
];

export default function Legend() {
  return (
    <div className="absolute bottom-8 left-4 bg-white rounded-lg shadow-lg p-4 z-10 text-xs">
      <p className="font-semibold text-gray-700 mb-2 text-[11px] uppercase tracking-wide">
        Grid Feasibility Index v1.0
      </p>
      <ul className="space-y-1.5">
        {CATEGORIES.map((cat) => (
          <li key={cat} className="flex items-center gap-2">
            <span
              className="inline-block w-3 h-3 rounded-sm flex-shrink-0"
              style={{ backgroundColor: FEASIBILITY_COLORS[cat] }}
            />
            <span className="text-gray-600 leading-tight">
              {FEASIBILITY_LABELS[cat]}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-gray-400 mt-3 text-[10px]">
        Data: EIA Form 861 + Berkeley Lab queue
      </p>
    </div>
  );
}
