/**
 * Stacked horizontal bar showing a relative breakdown across labeled
 * categories. Used by library-stats to show audio-format distribution
 * (mp3/m4a/flac/...) — but generic enough for any "share of total" view.
 */

export type FormatSegment = {
  label: string;
  value: number;
  /** Optional tooltip text; defaults to "<label>: <value>". */
  hint?: string;
};

function colorFor(i: number, total: number): string {
  const hue = (i * 360) / Math.max(total, 1);
  return `hsl(${hue} 60% 55%)`;
}

export function FormatBar({
  segments,
  height = 22,
}: {
  segments: FormatSegment[];
  height?: number;
}) {
  const total = segments.reduce((s, x) => s + Math.max(x.value, 0), 0);
  if (total <= 0) {
    return (
      <div style={{ opacity: 0.6, fontSize: 12 }}>No data to display.</div>
    );
  }

  const colored = segments.map((s, i) => ({
    ...s,
    color: colorFor(i, segments.length),
    share: s.value / total,
  }));

  return (
    <div>
      <div
        style={{
          display: 'flex',
          height,
          borderRadius: 4,
          overflow: 'hidden',
          background:
            'var(--color-background-tertiary, light-dark(#e5e5e5, #2c2c2c))',
        }}
      >
        {colored.map((s) => (
          <div
            key={s.label}
            style={{
              width: `${(s.share * 100).toFixed(2)}%`,
              height: '100%',
              background: s.color,
            }}
            title={s.hint ?? `${s.label}: ${s.value.toLocaleString()}`}
          />
        ))}
      </div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          marginTop: 8,
          fontSize: 12,
          opacity: 0.85,
        }}
      >
        {colored.map((s) => (
          <div
            key={s.label}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                background: s.color,
                flexShrink: 0,
              }}
            />
            <span>
              {s.label} · {s.value.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
