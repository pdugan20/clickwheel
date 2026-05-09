/**
 * Compact 2- or 4-column grid of headline stats. Each cell pairs a
 * large value with a small label. Reused by library-stats and
 * library-health.
 */
import type { CSSProperties } from 'react';

export type StatCell = {
  label: string;
  value: string;
  /** Optional accent color for the value (tone of voice — green=ok, red=warn). */
  tone?: 'default' | 'ok' | 'warn' | 'error';
};

const toneColor: Record<NonNullable<StatCell['tone']>, string> = {
  default: 'inherit',
  ok: 'var(--color-text-success, #16a34a)',
  warn: 'var(--color-text-warning, #ca8a04)',
  error: 'var(--color-text-danger, #dc2626)',
};

export function StatGrid({
  cells,
  columns = 'auto',
}: {
  cells: StatCell[];
  /** Number of grid columns; "auto" packs to the natural width. */
  columns?: number | 'auto';
}) {
  const gridTemplateColumns: CSSProperties['gridTemplateColumns'] =
    columns === 'auto'
      ? 'repeat(auto-fit, minmax(120px, 1fr))'
      : `repeat(${columns}, 1fr)`;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns,
        gap: 12,
      }}
    >
      {cells.map((c) => (
        <div
          key={c.label}
          style={{
            padding: 12,
            borderRadius: 'var(--border-radius-md, 8px)',
            background:
              'var(--color-background-secondary, light-dark(#fff, #232323))',
            border:
              '1px solid var(--color-border-secondary, light-dark(#e5e5e5, #2e2e2e))',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          <div
            style={{
              fontSize: 18,
              fontWeight: 600,
              color: toneColor[c.tone ?? 'default'],
              lineHeight: 1.2,
            }}
          >
            {c.value}
          </div>
          <div
            style={{
              fontSize: 11,
              opacity: 0.7,
              textTransform: 'uppercase',
              letterSpacing: 0.4,
            }}
          >
            {c.label}
          </div>
        </div>
      ))}
    </div>
  );
}
