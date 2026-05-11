/**
 * Stacked capacity bar segmented by top artists with free space on the
 * right. Designed for the iPod capacity view but reusable for any
 * "stuff on a fixed-size disk" payload.
 *
 * Segment hover surfaces a Floating UI tooltip (matching the library
 * format bar): artist + tracks · share-of-iPod.
 */
import { useEffect, useRef, useState } from 'react';
import { autoUpdate, offset, shift, useFloating } from '@floating-ui/react';

export type CapacityArtist = {
  artist: string;
  track_count: number;
};

export type CapacityBarProps = {
  capacity_bytes: number;
  used_bytes: number;
  free_bytes: number;
  top_artists: CapacityArtist[];
  /** Cap segments shown by name; remainder rolls into a single "other" stripe. */
  maxSegments?: number;
  /**
   * Called when the user clicks an artist in the legend. Wired by the
   * entry to `app.sendMessage` so the host treats it as a follow-up
   * prompt ("Show me Taylor Swift songs on my iPod").
   */
  onArtistClick?: (artist: string) => void;
};

function fmtBytes(n: number): string {
  if (!n && n !== 0) return '?';
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = n / 1024 ** 2;
  return `${mb.toFixed(0)} MB`;
}

function colorFor(i: number, total: number): string {
  const hue = (i * 360) / Math.max(total, 1);
  return `hsl(${hue} 60% 55%)`;
}

export function CapacityBar({
  capacity_bytes,
  used_bytes,
  free_bytes,
  top_artists,
  maxSegments = 8,
  onArtistClick,
}: CapacityBarProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const segmentRefs = useRef<(HTMLDivElement | null)[]>([]);
  const { refs, floatingStyles } = useFloating({
    placement: 'top',
    middleware: [offset(8), shift({ padding: 12 })],
    whileElementsMounted: autoUpdate,
  });
  useEffect(() => {
    refs.setReference(
      hovered === null ? null : (segmentRefs.current[hovered] ?? null)
    );
  }, [hovered, refs]);

  if (!capacity_bytes) {
    return <div style={{ opacity: 0.6 }}>No capacity data.</div>;
  }

  const named = top_artists.slice(0, maxSegments);
  const namedTracks = named.reduce((s, a) => s + (a.track_count || 0), 0);
  const allTracks = top_artists.reduce((s, a) => s + (a.track_count || 0), 0);
  const otherTracks = Math.max(allTracks - namedTracks, 0);
  const usedFraction = used_bytes / capacity_bytes;

  const segments = named.map((a, i) => {
    const share =
      allTracks > 0 ? (a.track_count / allTracks) * usedFraction : 0;
    return {
      name: a.artist,
      tracks: a.track_count,
      share,
      color: colorFor(i, named.length),
    };
  });
  if (otherTracks > 0) {
    segments.push({
      name: 'other artists',
      tracks: otherTracks,
      share: (otherTracks / allTracks) * usedFraction,
      color: 'light-dark(#9ca3af, #6b7280)',
    });
  }
  const freeFraction = free_bytes / capacity_bytes;

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: 10,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
          iPod capacity
        </h2>
        <div style={{ fontSize: 12, opacity: 0.7 }}>
          {fmtBytes(used_bytes)} used · {fmtBytes(free_bytes)} free ·{' '}
          {fmtBytes(capacity_bytes)} total
        </div>
      </div>
      <div style={{ position: 'relative' }}>
        <div
          style={{
            height: 22,
            borderRadius: 4,
            overflow: 'hidden',
            background: 'light-dark(#e5e5e5, #2c2c2c)',
            display: 'flex',
          }}
          onMouseLeave={() => setHovered(null)}
        >
          {segments.map((s, i) => (
            <div
              key={`${s.name}-${i}`}
              ref={(el) => {
                segmentRefs.current[i] = el;
              }}
              onMouseEnter={() => setHovered(i)}
              style={{
                width: `${(s.share * 100).toFixed(2)}%`,
                height: '100%',
                background: s.color,
                transition: 'filter 120ms',
                filter:
                  hovered !== null && hovered !== i
                    ? 'brightness(0.9)'
                    : 'none',
                cursor: 'default',
              }}
            />
          ))}
          <div
            style={{
              width: `${(freeFraction * 100).toFixed(2)}%`,
              height: '100%',
              background: 'transparent',
            }}
          />
        </div>
        {hovered !== null && segments[hovered] && (
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
            <span style={{ fontWeight: 600 }}>{segments[hovered].name}</span>
            <span style={{ fontWeight: 400, opacity: 0.75 }}>
              {' · '}
              {segments[hovered].tracks.toLocaleString()} tracks ·{' '}
              {(segments[hovered].share * 100).toFixed(1)}%
            </span>
          </div>
        )}
      </div>
      <div
        style={{
          marginTop: 10,
          display: 'flex',
          flexWrap: 'wrap',
          gap: '6px 16px',
          fontSize: 12,
          opacity: 0.85,
        }}
      >
        {segments.map((s, i) => {
          // The "other artists" rollup isn't a real artist, so it can't
          // turn into a follow-up prompt — render it inert.
          const clickable = !!onArtistClick && s.name !== 'other artists';
          const Pill = clickable ? 'button' : 'span';
          return (
            <Pill
              key={`${s.name}-${i}`}
              type={clickable ? 'button' : undefined}
              onClick={clickable ? () => onArtistClick!(s.name) : undefined}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: 'transparent',
                border: 'none',
                padding: 0,
                margin: 0,
                font: 'inherit',
                color: 'inherit',
                textAlign: 'left',
                cursor: clickable ? 'pointer' : 'default',
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  background: s.color,
                  flexShrink: 0,
                }}
              />
              <span>
                {s.name} · {s.tracks.toLocaleString()}
              </span>
            </Pill>
          );
        })}
      </div>
    </div>
  );
}
