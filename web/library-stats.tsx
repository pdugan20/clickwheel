/**
 * Library overview bundle. Finder-inspired layout — title + inline
 * subtitle of all the stats, then a stacked format-breakdown bar with
 * interior segment labels (only the wide ones show), then a dotted
 * legend. Consumes the library_stats tool's structured payload.
 *
 * Palette: monochromatic Focus blue (see lib/palette.ts). White
 * interior labels.
 */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp, useHostStyles } from '@modelcontextprotocol/ext-apps/react';
import {
  HeroFormatBar,
  LegendDots,
  type BarSegment,
} from './components/HeroFormatBar.js';
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
  const segments: BarSegment[] = formats.map((f) => ({
    label: f.format.toUpperCase(),
    value: f.count,
    hint: `${f.count.toLocaleString()} tracks · ${fmtBytes(f.total_bytes)}`,
  }));

  return (
    <div
      style={{
        ...rootStyle,
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      <div>
        <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>
          Music Library
        </div>
        <div style={{ fontSize: 12, opacity: 0.7, lineHeight: 1.5 }}>
          {stats.total_tracks.toLocaleString()} tracks ·{' '}
          {stats.artists.toLocaleString()} artists ·{' '}
          {stats.albums.toLocaleString()} albums · {fmtBytes(stats.total_bytes)}{' '}
          · {fmtHours(stats.total_seconds)} · {artworkPct.toFixed(0)}% artwork
        </div>
      </div>
      {segments.length > 0 && (
        <>
          <HeroFormatBar segments={segments} />
          <LegendDots segments={segments} />
        </>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LibraryStatsApp />
  </StrictMode>
);
