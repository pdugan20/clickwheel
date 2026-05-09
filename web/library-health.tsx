/**
 * Library health bundle: at-a-glance status of the library scan,
 * music-folder reachability, and missing-track count. Consumes the
 * library_health tool's structured payload.
 */
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp, useHostStyles } from '@modelcontextprotocol/ext-apps/react';
import { StatGrid, type StatCell } from './components/StatGrid.js';
import { rootStyle } from './lib/root-style.js';

type LibraryHealth = {
  library_dir: string;
  library_dir_exists: boolean;
  total_tracks: number;
  missing_tracks: number;
  last_scan_at: number | null;
  last_scan_iso?: string | null;
  auto_scan_enabled: boolean;
};

function fmtAge(timestampSec: number | null): string {
  if (!timestampSec) return 'never';
  const ageH = (Date.now() / 1000 - timestampSec) / 3600;
  if (ageH < 1) return `${Math.round(ageH * 60)} m ago`;
  if (ageH < 24) return `${ageH.toFixed(1)} h ago`;
  const ageD = ageH / 24;
  return `${ageD.toFixed(1)} d ago`;
}

function ageTone(timestampSec: number | null): StatCell['tone'] {
  if (!timestampSec) return 'error';
  const ageH = (Date.now() / 1000 - timestampSec) / 3600;
  if (ageH < 24) return 'ok';
  if (ageH < 24 * 7) return 'warn';
  return 'error';
}

function LibraryHealthApp() {
  const { app, isConnected, error } = useApp({
    appInfo: { name: 'clickwheel-library-health', version: '0.1.0' },
    capabilities: {},
  });
  useHostStyles(app);

  const [payload, setPayload] = useState<LibraryHealth | null>(null);

  useEffect(() => {
    if (!app) return;
    app.ontoolresult = (result) => {
      const sc = result?.structuredContent as LibraryHealth | undefined;
      if (sc?.library_dir != null) setPayload(sc);
    };
  }, [app]);

  if (error) return <div style={rootStyle}>Error: {error.message}</div>;
  if (!isConnected) return null;
  if (payload === null) {
    return <div style={rootStyle}>Waiting for health data…</div>;
  }

  const cells: StatCell[] = [
    {
      label: 'music folder',
      value: payload.library_dir_exists ? 'reachable' : 'missing',
      tone: payload.library_dir_exists ? 'ok' : 'error',
    },
    {
      label: 'tracks indexed',
      value: payload.total_tracks.toLocaleString(),
    },
    {
      label: 'missing files',
      value: payload.missing_tracks.toLocaleString(),
      tone: payload.missing_tracks === 0 ? 'ok' : 'warn',
    },
    {
      label: 'last scan',
      value: fmtAge(payload.last_scan_at),
      tone: ageTone(payload.last_scan_at),
    },
    {
      label: 'auto-scan',
      value: payload.auto_scan_enabled ? 'on' : 'off',
    },
  ];

  // Surface any actionable problems at the top, since the cells alone
  // can be cryptic when something's wrong.
  const issues: string[] = [];
  if (!payload.library_dir_exists) {
    issues.push(
      `Music folder "${payload.library_dir}" doesn't exist or isn't mounted.`
    );
  }
  if (payload.missing_tracks > 0) {
    issues.push(
      `${payload.missing_tracks.toLocaleString()} indexed tracks no longer exist on disk.`
    );
  }
  if (!payload.last_scan_at) {
    issues.push('Library has never been scanned. Run `clickwheel scan`.');
  }

  return (
    <div style={rootStyle}>
      <h2 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>
        Library health
      </h2>
      {issues.length > 0 && (
        <div
          style={{
            marginBottom: 12,
            padding: '8px 10px',
            borderRadius: 'var(--border-radius-sm, 6px)',
            background:
              'var(--color-background-warning, light-dark(#fef3c7, #3a2e0a))',
            color: 'var(--color-text-warning, #92400e)',
            fontSize: 12,
          }}
        >
          {issues.map((msg, i) => (
            <div key={i}>{msg}</div>
          ))}
        </div>
      )}
      <StatGrid cells={cells} />
      <div
        style={{
          marginTop: 10,
          fontSize: 11,
          opacity: 0.6,
          fontFamily: 'var(--font-mono, ui-monospace, monospace)',
        }}
      >
        {payload.library_dir}
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LibraryHealthApp />
  </StrictMode>
);
