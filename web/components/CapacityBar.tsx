/**
 * Stacked capacity bar segmented by top artists with free space on the
 * right. Designed for the iPod capacity view but reusable for any
 * "stuff on a fixed-size disk" payload.
 */

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
    return { name: a.artist, share, color: colorFor(i, named.length) };
  });
  if (otherTracks > 0) {
    segments.push({
      name: 'other artists',
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
          marginBottom: 8,
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
      <div
        style={{
          position: 'relative',
          height: 22,
          borderRadius: 4,
          overflow: 'hidden',
          background: 'light-dark(#e5e5e5, #2c2c2c)',
          display: 'flex',
        }}
      >
        {segments.map((s, i) => (
          <div
            key={`${s.name}-${i}`}
            style={{
              width: `${(s.share * 100).toFixed(2)}%`,
              height: '100%',
              background: s.color,
            }}
            title={`${s.name} — ${(s.share * 100).toFixed(1)}%`}
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
      <div
        style={{
          marginTop: 10,
          fontSize: 12,
          lineHeight: 1.5,
          opacity: 0.85,
        }}
      >
        {segments.map((s, i) => {
          // The "other artists" rollup isn't a real artist, so it can't
          // turn into a follow-up prompt — render it inert.
          const clickable = !!onArtistClick && s.name !== 'other artists';
          const Row = clickable ? 'button' : 'div';
          return (
            <Row
              key={`${s.name}-${i}`}
              type={clickable ? 'button' : undefined}
              onClick={clickable ? () => onArtistClick!(s.name) : undefined}
              style={{
                display: 'flex',
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
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: s.color,
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  textDecoration: clickable ? 'underline' : 'none',
                  textDecorationColor: 'currentcolor',
                  textDecorationStyle: 'dotted',
                  textUnderlineOffset: 3,
                }}
              >
                {s.name}
              </span>
            </Row>
          );
        })}
      </div>
    </div>
  );
}
