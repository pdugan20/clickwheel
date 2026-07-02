/**
 * Sync-result summary card. Bound to the destructive iPod-write tools
 * (sync_playlist_to_ipod, add_tracks_to_ipod, add_artist_to_ipod,
 * remove_*) and renders whichever flavor of result lands.
 *
 * Two render paths share one h2 14/600 header pattern (matching
 * library-stats / ipod-capacity):
 *   - "running" → live progress via TrackTicker (current + next-up
 *     queue label) above a thin progress bar.
 *   - "done" → inline stats summary on the right of the title plus a
 *     tone-coloured Badge ("ready to eject" / "X failed" / "no-op").
 *
 * The Pending component polls `state://clickwheel/sync-progress` to
 * advance the ticker mid-call. If Claude Desktop mounts the iframe
 * after the tool result is already in, the bundle skips Pending and
 * goes straight to the done state.
 */
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp, useHostStyles } from '@modelcontextprotocol/ext-apps/react';
import type { App } from '@modelcontextprotocol/ext-apps';
import { BRAND_BLUE, rootStyle } from './lib/root-style.js';

const PROGRESS_URI = 'state://clickwheel/sync-progress';
const POLL_INTERVAL_MS = 250;

type SyncProgress = {
  kind: 'idle' | 'sync' | 'add' | 'remove';
  current: number;
  total: number;
  message: string;
  /**
   * Static, human-readable subtitle describing the operation as a
   * whole — set once when the sync starts, never updated per track.
   * Examples: "About 145 MB · across 8 albums", "Single album · Pinkerton",
   * "12 tracks from 3 albums". Optional; falls back to no subtitle.
   */
  detail?: string;
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

/**
 * Right-slot status text — matches the inline-summary style used by
 * library-stats / ipod-capacity headers (12/0.7 plain text). Picks up
 * a tone color for warn/error so the signal still pops without the
 * heavy chip chrome that used to live here.
 */
function StatusLine({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'error';
  children: string;
}) {
  const color =
    tone === 'warn'
      ? 'var(--color-text-warning, #ca8a04)'
      : tone === 'error'
        ? 'var(--color-text-danger, #dc2626)'
        : undefined;
  return (
    <span
      style={{
        fontSize: 12,
        opacity: tone === 'ok' ? 0.7 : 1,
        color,
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
  if (p.conflict) return { tone: 'warn', text: 'Choose how to proceed' };
  if (p.library_updated === false) {
    return { tone: 'warn', text: 'Library not fully updated' };
  }
  if (p.failed && p.failed > 0) {
    return { tone: 'warn', text: `${p.failed} failed` };
  }
  if (p.synced === false) return { tone: 'ok', text: 'No-op' };
  return { tone: 'ok', text: 'Ready to eject' };
}

function deriveInlineStats(p: SyncResultPayload): string {
  // No-op sync (already in sync) — title says it; no breakdown needed.
  if (p.synced === false && !p.conflict) return '';
  // Removed-playlist artifact — no per-track stats.
  if (p.removed_playlist) return '';

  const parts: string[] = [];

  // Removal flavor.
  if (typeof p.removed === 'number') {
    parts.push(`${p.removed.toLocaleString()} removed`);
    if ((p.bytes_freed ?? 0) > 0) {
      parts.push(`${fmtBytes(p.bytes_freed ?? 0)} freed`);
    }
    if ((p.not_matched ?? 0) > 0) {
      parts.push(`${(p.not_matched ?? 0).toLocaleString()} not on iPod`);
    }
    return parts.join(' · ');
  }

  // Add / sync flavor.
  parts.push(`${(p.added ?? 0).toLocaleString()} added`);
  if ((p.already_present ?? 0) > 0) {
    parts.push(`${(p.already_present ?? 0).toLocaleString()} already on iPod`);
  }
  if ((p.also_on_ipod ?? 0) > 0) {
    parts.push(`${(p.also_on_ipod ?? 0).toLocaleString()} kept in place`);
  }
  if ((p.failed ?? 0) > 0) {
    parts.push(`${(p.failed ?? 0).toLocaleString()} failed`);
  }
  if (p.on_conflict) parts.push(`conflict: ${p.on_conflict}`);
  if (p.found_in_library != null && p.artist) {
    parts.push(`${p.found_in_library.toLocaleString()} in library`);
  }
  return parts.join(' · ');
}

function ProgressBar({ current, total }: { current: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (current / total) * 100) : 0;
  // Hard-code the track color rather than chaining through
  // var(--color-background-tertiary). Claude Desktop injects that
  // variable as a value very close to the card bg, making the track
  // disappear. Literal hex matches the visible gray we get in the
  // workbench (where the variable is unset and the fallback kicks in).
  return (
    <div
      style={{
        height: 8,
        borderRadius: 4,
        overflow: 'hidden',
        background: 'light-dark(#e5e5e5, #3a3a3a)',
      }}
    >
      <div
        style={{
          width: `${pct.toFixed(1)}%`,
          height: '100%',
          background: BRAND_BLUE,
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
  // Once we've observed an in-flight state we lock into "show progress"
  // mode. When done flips true, we keep the final bar visible until the
  // parent's ontoolresult swaps in the summary — without this, the
  // bundle flashes back to the generic placeholder copy for one frame
  // before the result lands.
  const [hasStarted, setHasStarted] = useState(false);

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
          if (!cancelled) {
            setProgress(parsed);
            if (parsed.kind !== 'idle' && parsed.total > 0) {
              setHasStarted(true);
            }
          }
        }
      } catch {
        // Polling is best-effort.
      }
    }

    tick();
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [app]);

  const showProgress = hasStarted && progress && progress.total > 0;

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
          // columnGap keeps the desktop title↔stats spacing on one line;
          // rowGap is the tighter gap used only when the stats wrap to a
          // second line on a narrow (mobile) viewport.
          columnGap: 12,
          rowGap: 4,
          flexWrap: 'wrap',
        }}
      >
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
          {progress
            ? `${verbForKind(progress.kind)} ${progress.operation || ''}`.trim()
            : 'Working on it…'}
        </h2>
        {showProgress && (
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            {progress!.current} of {progress!.total}
            {progress!.detail ? ` · ${progress!.detail}` : ''}
          </div>
        )}
      </div>
      {!showProgress && (
        <div style={{ fontSize: 12, opacity: 0.7 }}>
          The summary will appear here when the operation completes.
        </div>
      )}
      {showProgress && (
        <ProgressBar current={progress!.current} total={progress!.total} />
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
  const inlineStats = deriveInlineStats(payload);
  const rightText = inlineStats ? `${badge.text} · ${inlineStats}` : badge.text;
  // Mirror the Pending state's structure (header row + thin bar below)
  // so the iframe height stays stable across the live→done transition.
  // Only show the bar when actual track work happened — for no-op /
  // already-in-sync / conflict, the bar would be either misleading or
  // dominated by the conflict panel.
  const showCompletionBar =
    !payload.conflict &&
    ((payload.added ?? 0) > 0 || (payload.removed ?? 0) > 0);

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
          // columnGap keeps the desktop title↔stats spacing on one line;
          // rowGap is the tighter gap used only when the stats wrap to a
          // second line on a narrow (mobile) viewport.
          columnGap: 12,
          rowGap: 4,
          flexWrap: 'wrap',
        }}
      >
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{title}</h2>
        <StatusLine tone={badge.tone}>{rightText}</StatusLine>
      </div>
      {showCompletionBar && <ProgressBar current={1} total={1} />}
      {payload.conflict && (
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
      )}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SyncResultApp />
  </StrictMode>
);
