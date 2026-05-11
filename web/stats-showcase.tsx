/**
 * Workbench-only design showcase — palette round.
 *
 * We picked Variant D (Finder layout) from the last round. This file
 * now uses that same layout four times to compare bar palettes:
 *
 *   1. Brand — Anthropic earth tones (Book Cloth, Kraft, Manilla,
 *      Ivory Dark) with Focus blue as an accent. Warm, on-brand.
 *   2. Mono · Rust — shades of Book Cloth (#CC785C) from dark to
 *      light. Most cohesive, single hue.
 *   3. Mono · Focus blue — shades of Focus (#61AAF2). Cooler, more
 *      "Anthropic accent" feel.
 *   4. Mono · Cloud — shades of gray. Most subtle, dashboard-y.
 *
 * Once we pick a palette, this file gets deleted and the winner
 * propagates into the real bundles.
 */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp, useHostStyles } from '@modelcontextprotocol/ext-apps/react';
import { rootStyle } from './lib/root-style.js';

type Stats = {
  total_tracks: number;
  artists: number;
  albums: number;
  total_bytes: number;
  total_seconds: number;
  with_art: number;
  without_art: number;
};

type FormatRow = { format: string; count: number; total_bytes: number };
type Formats = FormatRow[];
type Payload = { stats: Stats; formats: Formats };

// ---------------------------------------------------------------------------
// Palettes.
// First entry of each list is the "largest segment" color — paint the
// dominant format in the strongest tone.
// ---------------------------------------------------------------------------

// 1. Brand: Anthropic earth tones + Focus accent for the tail.
const PALETTE_BRAND = [
  '#CC785C', // Book Cloth — rust
  '#D4A27F', // Kraft — tan
  '#EBDBBC', // Manilla — cream
  '#61AAF2', // Focus — blue accent on the long tail
  '#91918D', // Cloud Medium — fallback for 5th
  '#BFBFBA', // Cloud Light — fallback for 6th
  '#E5E4DF', // Ivory Dark — fallback for 7th
];

// 2. Mono rust: shades of Book Cloth #CC785C, dark → light.
const PALETTE_MONO_RUST = [
  '#9B5641', // darker rust
  '#CC785C', // book cloth
  '#DDA28A', // lighter
  '#EBC2B0', // lightest
  '#F5DCCB',
  '#F8E8DE',
  '#FBEFE8',
];

// 3. Mono Focus blue: shades from #61AAF2, dark → light.
const PALETTE_MONO_BLUE = [
  '#2C6FB8', // dark
  '#61AAF2', // focus
  '#8FC2F4', // lighter
  '#B7D7F7',
  '#D4E6FA',
  '#E5F0FC',
  '#F1F7FE',
];

// 4. Mono cloud: shades of gray.
const PALETTE_MONO_CLOUD = [
  '#666663', // cloud dark
  '#91918D', // cloud medium
  '#BFBFBA', // cloud light
  '#D9D9D5',
  '#E5E4DF', // ivory dark
  '#F0F0EB', // ivory medium
  '#FAFAF7', // ivory light
];

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

// ---------------------------------------------------------------------------
// Bar + legend
// ---------------------------------------------------------------------------

function HeroFormatBar({
  formats,
  palette,
  height = 26,
}: {
  formats: Formats;
  palette: string[];
  height?: number;
}) {
  const total = formats.reduce((s, f) => s + f.count, 0);
  if (total <= 0) return null;
  const segments = formats.map((f, i) => ({
    ...f,
    color: palette[i % palette.length],
    pct: (f.count / total) * 100,
  }));
  return (
    <div
      style={{
        display: 'flex',
        height,
        borderRadius: 6,
        overflow: 'hidden',
      }}
    >
      {segments.map((s) => (
        <div
          key={s.format}
          style={{
            width: `${s.pct.toFixed(2)}%`,
            height: '100%',
            background: s.color,
            display: 'flex',
            alignItems: 'center',
            paddingLeft: 10,
            paddingRight: 10,
            fontSize: 11,
            fontWeight: 600,
            color: '#ffffff',
            letterSpacing: 0.3,
            overflow: 'hidden',
            whiteSpace: 'nowrap',
          }}
          title={`${s.format.toUpperCase()} · ${s.count.toLocaleString()} tracks · ${fmtBytes(
            s.total_bytes
          )}`}
        >
          {s.pct >= 12 ? s.format.toUpperCase() : ''}
        </div>
      ))}
    </div>
  );
}

function LegendDots({
  formats,
  palette,
}: {
  formats: Formats;
  palette: string[];
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
      {formats.map((f, i) => (
        <span
          key={f.format}
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
          {f.format.toUpperCase()} · {f.count.toLocaleString()}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single variant — layout fixed (D from last round), palette is the var.
// ---------------------------------------------------------------------------

function PaletteVariant({
  title,
  palette,
  stats,
  formats,
}: { title: string; palette: string[] } & Payload) {
  const artworkPct = (stats.with_art / stats.total_tracks) * 100;
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: 0.8,
          textTransform: 'uppercase',
          opacity: 0.45,
        }}
      >
        {title}
      </div>
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
      <HeroFormatBar formats={formats} palette={palette} />
      <LegendDots formats={formats} palette={palette} />
    </section>
  );
}

function Divider() {
  return (
    <hr
      style={{
        border: 'none',
        borderTop:
          '1px dashed var(--color-border-secondary, light-dark(rgba(0,0,0,0.12), rgba(255,255,255,0.12)))',
        margin: '16px 0',
      }}
    />
  );
}

function ShowcaseApp() {
  const [payload, setPayload] = useState<Payload | null>(null);

  const { app, isConnected, error } = useApp({
    appInfo: { name: 'clickwheel-stats-showcase', version: '0.1.0' },
    capabilities: {},
    onAppCreated: (created) => {
      created.ontoolresult = (result) => {
        const sc = result?.structuredContent as Payload | undefined;
        if (sc?.stats?.total_tracks != null) setPayload(sc);
      };
    },
  });
  useHostStyles(app);

  if (error) return <div style={rootStyle}>Error: {error.message}</div>;
  if (!isConnected) return null;
  if (!payload) return <div style={rootStyle}>Waiting for data…</div>;

  return (
    <div
      style={{
        ...rootStyle,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <PaletteVariant
        title="1 — Brand (earth tones + Focus accent)"
        palette={PALETTE_BRAND}
        {...payload}
      />
      <Divider />
      <PaletteVariant
        title="2 — Mono · Book Cloth (rust)"
        palette={PALETTE_MONO_RUST}
        {...payload}
      />
      <Divider />
      <PaletteVariant
        title="3 — Mono · Focus (blue)"
        palette={PALETTE_MONO_BLUE}
        {...payload}
      />
      <Divider />
      <PaletteVariant
        title="4 — Mono · Cloud (gray)"
        palette={PALETTE_MONO_CLOUD}
        {...payload}
      />
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ShowcaseApp />
  </StrictMode>
);
