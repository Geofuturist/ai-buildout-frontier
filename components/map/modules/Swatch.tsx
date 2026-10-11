export default function Swatch({ color, stroke, dashed }: { color?: string; stroke?: string; dashed?: boolean }) {
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
