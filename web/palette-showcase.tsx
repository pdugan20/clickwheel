/**
 * Workbench-only design comparison view. Renders the capacity bar five
 * times against the same fixture data, each with a different
 * categorical palette, so we can eyeball which one we want to land as
 * the default. After we pick one, this file (and its html/fixtures
 * siblings) get deleted and the winner is propagated into CapacityBar.
 *
 * Excluded from production builds via
 * `web/scripts/inline_bundles.mjs`'s `-showcase.html` skip rule.
 */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp, useHostStyles } from '@modelcontextprotocol/ext-apps/react';
import { CapacityBar, type CapacityArtist } from './components/CapacityBar.js';
import { rootStyle } from './lib/root-style.js';

type IpodContents = {
  capacity_bytes: number;
  used_bytes: number;
  free_bytes: number;
  top_artists: CapacityArtist[];
};

type Palette = {
  name: string;
  note: string;
  /** Empty array = use the component's HSL fallback (the "current" behaviour). */
  colors: readonly string[];
};

// 5 candidates worth comparing side-by-side. Stay in this order: control
// first, then the two academic standards, then the brand-aligned option.
const PALETTES: Palette[] = [
  {
    name: 'Current (HSL rainbow)',
    note: 'evenly-spaced hues — produces the "two greens close together" problem at i=2 and i=3',
    colors: [],
  },
  {
    name: 'Tableau 10',
    note: 'the practical workhorse — high contrast, no two adjacent colors confusable',
    colors: [
      '#4E79A7',
      '#F28E2B',
      '#E15759',
      '#76B7B2',
      '#59A14F',
      '#EDC948',
      '#B07AA1',
      '#FF9DA7',
    ],
  },
  {
    name: 'Okabe-Ito',
    note: 'designed for color-vision deficiency (Okabe & Ito 2008) — the academic gold standard',
    colors: [
      '#E69F00',
      '#56B4E9',
      '#009E73',
      '#F0E442',
      '#0072B2',
      '#D55E00',
      '#CC79A7',
      '#999999',
    ],
  },
  {
    name: 'Tol Bright',
    note: 'Paul Tol’s colorblind-safe palette — more saturated than Okabe-Ito',
    colors: [
      '#4477AA',
      '#EE6677',
      '#228833',
      '#CCBB44',
      '#66CCEE',
      '#AA3377',
      '#BBBBBB',
    ],
  },
  {
    name: 'Anthropic warm',
    note: 'Book Cloth, Kraft, Manilla, Focus blue + Cloud grays on the long tail',
    colors: [
      '#CC785C',
      '#D4A27F',
      '#EBDBBC',
      '#61AAF2',
      '#91918D',
      '#666663',
      '#BFBFBA',
      '#E5E4DF',
    ],
  },
  {
    name: 'Magenta → aqua spectrum',
    note: 'single-hue progression from raspberry through indigo to sky aqua',
    colors: [
      '#B5179E',
      '#7209B7',
      '#560BAD',
      '#480CA8',
      '#3A0CA3',
      '#3F37C9',
      '#4361EE',
      '#4895EF',
      '#4CC9F0',
    ],
  },
  {
    name: 'Pastel rainbow (warmer)',
    note: 'punchier pastels: blush, apricot, cream, tea green, aqua, baby blue, periwinkle, mauve',
    colors: [
      '#FFADAD',
      '#FFD6A5',
      '#FDFFB6',
      '#CAFFBF',
      '#9BF6FF',
      '#A0C4FF',
      '#BDB2FF',
      '#FFC6FF',
      '#FFFFFC',
    ],
  },
  {
    name: 'Sunset bold',
    note: 'saturated 5-stop: navy, dark raspberry, hot fuchsia, blaze orange, amber gold (wraps at i=5)',
    colors: ['#390099', '#9E0059', '#FF0054', '#FF5400', '#FFBD00'],
  },
  {
    name: 'Vibrant 5',
    note: 'amber, orange, neon pink, blue-violet, azure — cleaner hue separation than Sunset bold (also wraps at i=5)',
    colors: ['#FFBE0B', '#FB5607', '#FF006E', '#8338EC', '#3A86FF'],
  },
  {
    name: 'Balanced 5',
    note: 'bubblegum pink, golden pollen, emerald, ocean blue, dark teal — broad hue spread (wraps at i=5)',
    colors: ['#EF476F', '#FFD166', '#06D6A0', '#118AB2', '#073B4C'],
  },
];

function PaletteSection({
  title,
  note,
  colors,
  payload,
}: {
  title: string;
  note: string;
  colors: readonly string[];
  payload: IpodContents;
}) {
  return (
    <section
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        padding: '14px 0',
        borderTop:
          '1px dashed light-dark(rgba(0,0,0,0.10), rgba(255,255,255,0.10))',
      }}
    >
      <div>
        <div
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: 0.6,
            opacity: 0.55,
            marginBottom: 2,
          }}
        >
          {title}
        </div>
        <div style={{ fontSize: 12, opacity: 0.7, lineHeight: 1.4 }}>
          {note}
        </div>
      </div>
      <CapacityBar
        capacity_bytes={payload.capacity_bytes}
        used_bytes={payload.used_bytes}
        free_bytes={payload.free_bytes}
        top_artists={payload.top_artists}
        palette={colors.length > 0 ? colors : undefined}
      />
    </section>
  );
}

function ShowcaseApp() {
  const [payload, setPayload] = useState<IpodContents | null>(null);

  const { app, isConnected, error } = useApp({
    appInfo: { name: 'clickwheel-palette-showcase', version: '0.1.0' },
    capabilities: {},
    onAppCreated: (created) => {
      created.ontoolresult = (result) => {
        const sc = result?.structuredContent as IpodContents | undefined;
        if (sc?.capacity_bytes != null) setPayload(sc);
      };
    },
  });
  useHostStyles(app);

  if (error) return <div style={rootStyle}>Error: {error.message}</div>;
  if (!isConnected) return null;
  if (!payload) return <div style={rootStyle}>Waiting for fixture data…</div>;

  return (
    <div
      style={{
        ...rootStyle,
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      }}
    >
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
          Capacity-bar palette comparison
        </div>
        <div style={{ fontSize: 12, opacity: 0.7 }}>
          Same fixture, five categorical palettes. Pick the one that reads
          cleanest at small segment widths and stays distinct across light /
          dark mode.
        </div>
      </div>
      {PALETTES.map((p) => (
        <PaletteSection
          key={p.name}
          title={p.name}
          note={p.note}
          colors={p.colors}
          payload={payload}
        />
      ))}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ShowcaseApp />
  </StrictMode>
);
