import type { Meta } from '@/lib/data';
import { COLORS, VOLTAGE_BANDS, legendClasses } from '@/lib/style';

function Swatch({ color, stroke, dashed }: { color?: string; stroke?: string; dashed?: boolean }) {
  return (
    <span
      aria-hidden
      className="inline-block h-4 w-6 shrink-0 rounded-sm"
      style={{
        background: color ?? 'transparent',
        border: `1px ${dashed ? 'dashed' : 'solid'} ${stroke ?? 'transparent'}`,
      }}
    />
  );
}

export default function Legend({ meta, showLines }: { meta: Meta | null; showLines: boolean }) {
  const d = meta?.display;
  const classes = d && d.breaks && d.value_field ? legendClasses(d.breaks, d.unit ?? '', Boolean(d.zero_class)) : [];
  return (
    <section aria-label="Legend" className="text-sm">
      {meta && classes.length > 0 && (
        <>
          <h3 className="mb-1 text-[13px] font-semibold text-ink">{d?.legend_title}</h3>
          <ul className="space-y-1">
            {classes.map((c) => (
              <li key={c.label} className="flex items-center gap-2">
                <Swatch color={c.color} stroke={c.color === COLORS.zero ? COLORS.zeroStroke : undefined} />
                <span>{c.label}</span>
              </li>
            ))}
            <li className="flex items-center gap-2">
              <Swatch color={COLORS.noValue} />
              <span>Covered, no value in the source</span>
            </li>
            <li className="flex items-center gap-2">
              <Swatch stroke={COLORS.notCovered} dashed />
              <span>Not covered (no fill, dashed outline)</span>
            </li>
          </ul>
        </>
      )}
      {showLines && (
        <>
          <h3 className="mb-1 mt-3 text-[13px] font-semibold text-ink">Transmission line voltage</h3>
          <ul className="space-y-1">
            {VOLTAGE_BANDS.map((b) => (
              <li key={b.id} className="flex items-center gap-2">
                <svg width="24" height="10" aria-hidden className="shrink-0">
                  <line
                    x1="0" y1="5" x2="24" y2="5"
                    stroke={b.color}
                    strokeWidth={Math.max(1.5, b.width * 1.6)}
                    strokeDasharray={b.dashed ? '4 3' : undefined}
                  />
                </svg>
                <span>{b.label}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-3 text-xs text-muted">Layers are named after their source.</p>
      <p className="mt-1 text-xs text-muted">
        Boundaries follow the US government&apos;s point of view and do not express a position of the project.
      </p>
    </section>
  );
}
