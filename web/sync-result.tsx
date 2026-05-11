/**
 * Sync-result summary card. Bound to the three destructive iPod-write
 * tools — sync_playlist_to_ipod, add_tracks_to_ipod, add_artist_to_ipod
 * — and renders whichever flavor of result lands.
 *
 * Renders three states:
 *   - "no payload yet" → empty placeholder. This is the state we
 *     deliberately keep visible if Claude Desktop mounts the iframe
 *     mid-call (the preload experiment). If the user sees this state
 *     during a long-running sync, we know preload works and can layer
 *     polling-based live progress on top later.
 *   - "running" / "no data" → a spinner-ish "preparing summary" hint.
 *   - "done" → the actual stats card.
 */
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp, useHostStyles } from '@modelcontextprotocol/ext-apps/react';
import type { App } from '@modelcontextprotocol/ext-apps';
import { StatGrid, type StatCell } from './components/StatGrid.js';
import { rootStyle } from './lib/root-style.js';

const PROGRESS_URI = 'state://clickwheel/sync-progress';
const POLL_INTERVAL_MS = 500;

type SyncProgress = {
  kind: 'idle' | 'sync' | 'add' | 'remove';
  current: number;
  total: number;
  message: string;
  operation: string;
  done: boolean;
};

// All three tools share these fields, with sync_playlist also reporting
// the playlist names. We accept the superset; missing keys are rendered
// as `null` or skipped.
type SyncResultPayload = {
  // Common across tools.
  added?: number;
  failed?: number;
  library_updated?: boolean;
  // sync_playlist_to_ipod
  synced?: boolean;
  playlist?: string;
  ipod_playlist?: string;
  on_conflict?: string | null;
  also_on_ipod?: number;
  conflict?: {
    existing_name: string;
    existing_track_count: number;
    message?: string;
  };
  // add_tracks_to_ipod / add_artist_to_ipod
  already_present?: number;
  artist?: string;
  found_in_library?: number;
  // remove_tracks_from_ipod / remove_artist_from_ipod
  removed?: number;
  not_matched?: number;
  bytes_freed?: number;
  // remove_ipod_playlist
  removed_playlist?: boolean;
};

function fmtCount(n: number, singular: string, plural?: string): string {
  return `${n.toLocaleString()} ${n === 1 ? singular : (plural ?? singular + 's')}`;
}

function Badge({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'error';
  children: string;
}) {
  const bg = {
    ok: 'var(--color-background-success, light-dark(#dcfce7, #14532d))',
    warn: 'var(--color-background-warning, light-dark(#fef3c7, #3a2e0a))',
    error: 'var(--color-background-danger, light-dark(#fee2e2, #4a0e0e))',
  }[tone];
  const fg = {
    ok: 'var(--color-text-success, #15803d)',
    warn: 'var(--color-text-warning, #92400e)',
    error: 'var(--color-text-danger, #b91c1c)',
  }[tone];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 999,
        background: bg,
        color: fg,
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: 0.4,
      }}
    >
      {children}
    </span>
  );
}

function fmtBytes(n: number): string {
  if (!n) return '0 B';
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = n / 1024 ** 2;
  if (mb >= 1) return `${mb.toFixed(0)} MB`;
  return `${Math.round(n / 1024)} KB`;
}

function deriveTitle(p: SyncResultPayload): string {
  if (p.conflict) return `Playlist name conflict`;
  if (p.removed_playlist && p.ipod_playlist) {
    return `Removed playlist "${p.ipod_playlist}"`;
  }
  if (typeof p.removed === 'number') {
    if (p.artist) return `Removed ${p.artist} from the iPod`;
    return `Removed tracks from the iPod`;
  }
  if (p.synced === false && !p.conflict) return `Already in sync`;
  if (p.synced) {
    const target = p.ipod_playlist ?? p.playlist ?? 'playlist';
    return `Synced playlist "${target}"`;
  }
  if (p.artist) {
    return `Added ${p.artist}`;
  }
  return `Added tracks to the iPod`;
}

function deriveBadge(p: SyncResultPayload): {
  tone: 'ok' | 'warn' | 'error';
  text: string;
} {
  if (p.conflict) return { tone: 'warn', text: 'choose how to proceed' };
  if (p.library_updated === false) {
    return { tone: 'warn', text: 'library not fully updated' };
  }
  if (p.failed && p.failed > 0) {
    return { tone: 'warn', text: `${p.failed} failed` };
  }
  if (p.synced === false) return { tone: 'ok', text: 'no-op' };
  return { tone: 'ok', text: 'ready to eject' };
}

function deriveCells(p: SyncResultPayload): StatCell[] {
  // Removal payload — present its own stats.
  if (typeof p.removed === 'number') {
    const cells: StatCell[] = [
      {
        label: 'removed',
        value: p.removed.toLocaleString(),
        tone: p.removed > 0 ? 'ok' : 'default',
      },
    ];
    if ((p.bytes_freed ?? 0) > 0) {
      cells.push({
        label: 'freed',
        value: fmtBytes(p.bytes_freed ?? 0),
      });
    }
    if ((p.not_matched ?? 0) > 0) {
      cells.push({
        label: 'not on iPod',
        value: (p.not_matched ?? 0).toLocaleString(),
        tone: 'warn',
      });
    }
    return cells;
  }

  // Add / sync payload.
  const cells: StatCell[] = [];
  const added = p.added ?? 0;
  cells.push({
    label: 'added',
    value: added.toLocaleString(),
    tone: added > 0 ? 'ok' : 'default',
  });
  if ((p.already_present ?? 0) > 0) {
    cells.push({
      label: 'already on iPod',
      value: (p.already_present ?? 0).toLocaleString(),
    });
  }
  if ((p.also_on_ipod ?? 0) > 0) {
    cells.push({
      label: 'kept in place',
      value: (p.also_on_ipod ?? 0).toLocaleString(),
    });
  }
  if ((p.failed ?? 0) > 0) {
    cells.push({
      label: 'failed',
      value: (p.failed ?? 0).toLocaleString(),
      tone: 'error',
    });
  }
  if (p.on_conflict) {
    cells.push({ label: 'conflict', value: p.on_conflict });
  }
  if (p.found_in_library != null && p.artist) {
    cells.push({
      label: 'in library',
      value: p.found_in_library.toLocaleString(),
    });
  }
  return cells;
}

function ProgressBar({ current, total }: { current: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (current / total) * 100) : 0;
  return (
    <div
      style={{
        height: 8,
        borderRadius: 4,
        overflow: 'hidden',
        background:
          'var(--color-background-tertiary, light-dark(#e5e5e5, #2c2c2c))',
      }}
    >
      <div
        style={{
          width: `${pct.toFixed(1)}%`,
          height: '100%',
          background:
            'var(--color-background-success, light-dark(#22c55e, #15803d))',
          transition: 'width 200ms linear',
        }}
      />
    </div>
  );
}

function verbForKind(kind: SyncProgress['kind']): string {
  if (kind === 'sync') return 'Syncing';
  if (kind === 'add') return 'Adding';
  if (kind === 'remove') return 'Removing';
  return 'Working on it';
}

function Pending({ app }: { app: App | null }) {
  const [progress, setProgress] = useState<SyncProgress | null>(null);

  useEffect(() => {
    if (!app) return;
    let cancelled = false;

    async function tick() {
      if (!app || cancelled) return;
      try {
        const res = await app.readServerResource({ uri: PROGRESS_URI });
        const body = res?.contents?.[0];
        const text =
          body && 'text' in body && typeof body.text === 'string'
            ? body.text
            : null;
        if (text) {
          const parsed = JSON.parse(text) as SyncProgress;
          if (!cancelled) setProgress(parsed);
        }
      } catch {
        // Polling is best-effort; the iframe still renders the
        // generic "Working on it..." copy if the resource is
        // unreadable for some reason.
      }
    }

    tick();
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [app]);

  const hasProgress =
    progress &&
    progress.kind !== 'idle' &&
    !progress.done &&
    progress.total > 0;

  return (
    <div
      style={{
        ...rootStyle,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          gap: 12,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600 }}>
          {progress
            ? `${verbForKind(progress.kind)} ${progress.operation || ''}`.trim()
            : 'Working on it…'}
        </div>
        {hasProgress && (
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            {progress!.current} / {progress!.total}
          </div>
        )}
      </div>
      {hasProgress && (
        <>
          <ProgressBar current={progress!.current} total={progress!.total} />
          <div
            style={{
              fontSize: 12,
              opacity: 0.85,
              fontFamily:
                'var(--font-mono, ui-monospace, "SF Mono", Menlo, monospace)',
            }}
          >
            {progress!.message || ' '}
          </div>
        </>
      )}
      {!hasProgress && (
        <div style={{ fontSize: 12, opacity: 0.7 }}>
          The summary will appear here when the operation completes.
        </div>
      )}
    </div>
  );
}

function SyncResultApp() {
  const [payload, setPayload] = useState<SyncResultPayload | null>(null);

  const { app, isConnected, error } = useApp({
    appInfo: { name: 'clickwheel-sync-result', version: '0.1.0' },
    capabilities: {},
    onAppCreated: (created) => {
      created.ontoolresult = (result) => {
        const sc = result?.structuredContent as SyncResultPayload | undefined;
        if (sc) setPayload(sc);
      };
    },
  });
  useHostStyles(app);

  if (error) {
    return <div style={rootStyle}>Error: {error.message}</div>;
  }
  if (!isConnected) return null;
  if (payload === null) return <Pending app={app} />;

  const title = deriveTitle(payload);
  const badge = deriveBadge(payload);
  const cells = deriveCells(payload);

  return (
    <div style={rootStyle}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: 12,
          gap: 12,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h2>
        <Badge tone={badge.tone}>{badge.text}</Badge>
      </div>
      {payload.conflict ? (
        <div
          style={{
            padding: '10px 12px',
            borderRadius: 'var(--border-radius-sm, 6px)',
            background:
              'var(--color-background-warning, light-dark(#fef3c7, #3a2e0a))',
            color: 'var(--color-text-warning, #92400e)',
            fontSize: 12,
            lineHeight: 1.4,
          }}
        >
          {`A playlist named "${payload.conflict.existing_name}" already exists on the iPod with ${fmtCount(payload.conflict.existing_track_count, 'track')}. Pick merge, replace, or rename to continue.`}
        </div>
      ) : cells.length > 0 ? (
        <StatGrid cells={cells} />
      ) : null}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SyncResultApp />
  </StrictMode>
);
