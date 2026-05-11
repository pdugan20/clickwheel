/**
 * Finder-style stacked storage bar — no inline labels, custom tooltip
 * on hover.
 *
 * Each segment's width is proportional to its `value`. On hover, a
 * small dark tooltip pops above the segment with the label + hint.
 *
 * Positioning is delegated to Floating UI (`@floating-ui/react`):
 *   - offset(8)             keeps an 8px gap between bar and tooltip
 *   - shift({ padding: 12 }) slides the tooltip horizontally so it
 *                            never overflows the iframe viewport
 *
 * Placement is fixed to `top` (no `flip`) so the tooltip is
 * consistent across bundles. The tooltip is a single line, so it fits
 * comfortably above the bar even when the bar is near the top of the
 * iframe.
 *
 * We use `refs.setReference` to retarget Floating UI at the currently-
 * hovered segment, so one tooltip element follows multiple anchors.
 */
import { useEffect, useRef, useState } from 'react';
import { autoUpdate, offset, shift, useFloating } from '@floating-ui/react';
import { MONO_BLUE } from '../lib/palette.js';

export type BarSegment = {
  /** Short label (e.g. "MP3", "M4A"). Shown in the legend + tooltip. */
  label: string;
  /** Numeric weight that determines segment width. */
  value: number;
  /** Optional fully-rendered hint shown in the tooltip's second line. */
  hint?: string;
};

export function HeroFormatBar({
  segments,
  palette = MONO_BLUE,
  height = 26,
}: {
  segments: BarSegment[];
  palette?: readonly string[];
  height?: number;
}) {
  const [hovered, setHovered] = useState<number | null>(null);
  const segmentRefs = useRef<(HTMLDivElement | null)[]>([]);

  const { refs, floatingStyles } = useFloating({
    placement: 'top',
    middleware: [offset(8), shift({ padding: 12 })],
    whileElementsMounted: autoUpdate,
  });

  // Retarget the floating element at whichever segment is hovered.
  useEffect(() => {
    refs.setReference(
      hovered === null ? null : (segmentRefs.current[hovered] ?? null)
    );
  }, [hovered, refs]);

  const total = segments.reduce((s, x) => s + Math.max(x.value, 0), 0);
  if (total <= 0) return null;

  const enriched = segments.map((s, i) => ({
    ...s,
    color: palette[i % palette.length],
    pct: (s.value / total) * 100,
  }));

  const active = hovered !== null ? enriched[hovered] : null;

  return (
    <div style={{ position: 'relative' }}>
      <div
        style={{
          display: 'flex',
          height,
          borderRadius: 6,
          overflow: 'hidden',
        }}
        onMouseLeave={() => setHovered(null)}
      >
        {enriched.map((s, i) => (
          <div
            key={s.label}
            ref={(el) => {
              segmentRefs.current[i] = el;
            }}
            onMouseEnter={() => setHovered(i)}
            style={{
              width: `${s.pct.toFixed(2)}%`,
              height: '100%',
              background: s.color,
              transition: 'filter 120ms',
              filter:
                hovered !== null && hovered !== i ? 'brightness(0.9)' : 'none',
              cursor: 'default',
            }}
          />
        ))}
      </div>
      {active && (
        <div
          ref={refs.setFloating}
          style={{
            ...floatingStyles,
            pointerEvents: 'none',
            background:
              'var(--color-background-inverse, light-dark(#1f1e1d, #f0f0eb))',
            color: 'var(--color-text-inverse, light-dark(#fcfcfc, #1f1e1d))',
            padding: '6px 10px',
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 500,
            lineHeight: 1.3,
            whiteSpace: 'nowrap',
            boxShadow: '0 4px 12px rgba(0,0,0,0.18)',
            zIndex: 10,
          }}
        >
          <span style={{ fontWeight: 600 }}>{active.label}</span>
          <span style={{ fontWeight: 400, opacity: 0.75 }}>
            {' · '}
            {active.hint ??
              `${active.value.toLocaleString()} · ${active.pct.toFixed(1)}%`}
          </span>
        </div>
      )}
    </div>
  );
}

export function LegendDots({
  segments,
  palette = MONO_BLUE,
}: {
  segments: BarSegment[];
  palette?: readonly string[];
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '6px 16px',
        fontSize: 12,
        opacity: 0.85,
      }}
    >
      {segments.map((s, i) => (
        <span
          key={s.label}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              background: palette[i % palette.length],
              flexShrink: 0,
            }}
          />
          {s.label} · {s.value.toLocaleString()}
        </span>
      ))}
    </div>
  );
}
