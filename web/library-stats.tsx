/**
 * Library overview bundle: total counts, size, listening hours, and a
 * format-breakdown bar. Consumes the library_stats tool's structured
 * payload.
 */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp, useHostStyles } from '@modelcontextprotocol/ext-apps/react';
import { StatGrid } from './components/StatGrid.js';
import { FormatBar } from './components/FormatBar.js';
import { rootStyle } from './lib/root-style.js';

type LibraryStats = {
  stats: {
    total_tracks: number;
    artists: number;
    albums: number;
    total_bytes: number;
    total_seconds: number;
    with_art: number;
    without_art: number;
    missing_genre: number;
    missing_title: number;
    missing_artist: number;
  };
  formats: { format: string; count: number; total_bytes: number }[];
};

function fmtBytes(n: number): string {
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = n / 1024 ** 2;
  if (mb >= 1) return `${mb.toFixed(0)} MB`;
  return `${(n / 1024).toFixed(0)} KB`;
}

function fmtHours(seconds: number): string {
  const h = seconds / 3600;
  if (h >= 1) return `${h.toFixed(0)} h`;
  return `${Math.round(seconds / 60)} m`;
}

function LibraryStatsApp() {
  // ontoolresult is registered via onAppCreated rather than a post-mount
  // useEffect — see ipod-capacity.tsx for the rationale.
  const [payload, setPayload] = useState<LibraryStats | null>(null);

  const { app, isConnected, error } = useApp({
    appInfo: { name: 'clickwheel-library-stats', version: '0.1.0' },
    capabilities: {},
    onAppCreated: (created) => {
      created.ontoolresult = (result) => {
        const sc = result?.structuredContent as LibraryStats | undefined;
        if (sc?.stats?.total_tracks != null) setPayload(sc);
      };
    },
  });
  useHostStyles(app);

  if (error) return <div style={rootStyle}>Error: {error.message}</div>;
  if (!isConnected) return null;
  if (payload === null) {
    return <div style={rootStyle}>Waiting for library data…</div>;
  }

  const { stats, formats } = payload;
  if (!stats.total_tracks) {
    return (
      <div style={rootStyle}>
        Library is empty. Run <code>clickwheel scan</code> to index music.
      </div>
    );
  }

  const artworkPct = (stats.with_art / stats.total_tracks) * 100;
  const cells = [
    { label: 'tracks', value: stats.total_tracks.toLocaleString() },
    { label: 'artists', value: stats.artists.toLocaleString() },
    { label: 'albums', value: stats.albums.toLocaleString() },
    { label: 'size', value: fmtBytes(stats.total_bytes) },
    { label: 'duration', value: fmtHours(stats.total_seconds) },
    {
      label: 'artwork',
      value: `${artworkPct.toFixed(0)}%`,
      tone: (artworkPct >= 90 ? 'ok' : artworkPct >= 70 ? 'warn' : 'error') as
        | 'ok'
        | 'warn'
        | 'error',
    },
  ];

  return (
    <div style={rootStyle}>
      <h2 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>
        Library overview
      </h2>
      <StatGrid cells={cells} />
      {formats.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div
            style={{
              fontSize: 11,
              opacity: 0.7,
              textTransform: 'uppercase',
              letterSpacing: 0.4,
              marginBottom: 6,
            }}
          >
            Format breakdown
          </div>
          <FormatBar
            segments={formats.map((f) => ({
              label: f.format.toUpperCase(),
              value: f.count,
              hint: `${f.format.toUpperCase()} · ${f.count.toLocaleString()} tracks · ${fmtBytes(f.total_bytes)}`,
            }))}
          />
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LibraryStatsApp />
  </StrictMode>
);
