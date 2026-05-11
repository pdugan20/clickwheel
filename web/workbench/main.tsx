/**
 * Local design workbench for clickwheel MCP Apps bundles.
 *
 * Mounts the production bundle's HTML entry inside an iframe and plays
 * the host side of the MCP Apps protocol against it: responds to the
 * `ui/initialize` request with a stub host context, accepts size-changed
 * notifications, and pushes a fake `ui/notifications/tool-result`
 * carrying the selected fixture's structuredContent.
 *
 * This exercises the same connect/handshake/render path that Claude
 * Desktop will use, just with manual fixture data instead of a real
 * tool call. Iterate on components in `web/components/`, save, and
 * Vite's HMR re-mounts the bundle automatically.
 *
 * Sequencing: the SDK only accepts tool-result notifications after it
 * has sent `ui/notifications/initialized`, so we wait for that
 * notification before flushing the first fixture. After that, switching
 * fixtures pushes immediately (the iframe is still alive and connected).
 * Hitting "reload iframe" remounts the iframe and starts the handshake
 * over.
 */
import { StrictMode, useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { bundles, type Bundle } from './registry.js';
import type { Fixture } from '../ipod-capacity.fixtures.js';

const PROTOCOL_VERSION = '2026-01-26';

function buildHostResponse(theme: 'light' | 'dark') {
  return {
    protocolVersion: PROTOCOL_VERSION,
    hostInfo: { name: 'clickwheel-workbench', version: '0.1.0' },
    hostCapabilities: {
      openLinks: {},
      logging: {},
      sandbox: {},
    },
    hostContext: {
      theme,
      platform: 'desktop',
      locale: navigator.language,
    },
  };
}

type Status =
  | 'mounting'
  | 'awaiting-initialize'
  | 'initialized'
  | 'running-progress'
  | 'pushed-result';

const PROGRESS_URI = 'state://clickwheel/sync-progress';

type MockProgress = {
  kind: string;
  current: number;
  total: number;
  message: string;
  operation: string;
  done: boolean;
};

function idleProgress(): MockProgress {
  return {
    kind: 'idle',
    current: 0,
    total: 0,
    message: '',
    operation: '',
    done: true,
  };
}

type Viewport = 'mobile' | 'tablet' | 'desktop';
type Theme = 'light' | 'dark';

const VIEWPORT_WIDTHS: Record<Viewport, number> = {
  mobile: 380,
  tablet: 600,
  desktop: 720,
};

function ToggleGroup({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span
        style={{
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: 0.4,
          opacity: 0.6,
        }}
      >
        {label}
      </span>
      <div
        style={{
          display: 'inline-flex',
          background: 'light-dark(rgba(0,0,0,0.04), rgba(255,255,255,0.06))',
          borderRadius: 6,
          padding: 2,
        }}
      >
        {options.map((o) => {
          const active = o.value === value;
          return (
            <button
              key={o.value}
              onClick={() => onChange(o.value)}
              type="button"
              aria-pressed={active}
              style={{
                padding: '4px 10px',
                fontSize: 12,
                fontWeight: 500,
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
                background: active
                  ? 'light-dark(#fff, rgba(255,255,255,0.12))'
                  : 'transparent',
                color: 'inherit',
                boxShadow: active ? '0 1px 2px rgba(0,0,0,0.08)' : undefined,
              }}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Workbench() {
  const [bundle, setBundle] = useState<Bundle>(bundles[0]);
  const [fixture, setFixture] = useState<Fixture>(bundles[0].fixtures[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<Status>('mounting');
  const [viewport, setViewport] = useState<Viewport>('desktop');
  const [theme, setTheme] = useState<Theme>(
    matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  );

  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  // Apply theme to the workbench chrome (host doc). The iframe gets a
  // separate hostcontextchanged notification — handled below.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  // Keep latest theme in a ref so the message handler (registered once
  // with [] deps for stability) can read it on every ui/initialize
  // round-trip without re-binding.
  const themeRef = useRef(theme);
  themeRef.current = theme;

  // Broadcast theme changes to the iframe via hostcontextchanged so
  // the bundle's useHostStyles can re-apply colors live.
  useEffect(() => {
    const target = iframeRef.current?.contentWindow;
    if (!target || !initializedRef.current) return;
    target.postMessage(
      {
        jsonrpc: '2.0',
        method: 'ui/notifications/host-context-changed',
        params: { theme },
      },
      '*'
    );
  }, [theme]);

  // Keep the *latest* fixture in a ref synced on every render. The
  // listener and the post-init send both read from here so they can
  // never push a stale fixture, regardless of effect-ordering races.
  const fixtureRef = useRef(fixture);
  fixtureRef.current = fixture;

  // Per-iframe-instance gate. Resets to false whenever the iframe
  // remounts (bundle/reloadKey change), so the next ui/initialize
  // re-triggers a tool-result.
  const initializedRef = useRef(false);

  // Mock state for the workbench's stand-in `state://clickwheel/sync-
  // progress` MCP resource. Lives in a ref so the message handler
  // (registered once) always reads the latest.
  const mockProgressRef = useRef<MockProgress>(idleProgress());
  // Timer that ticks the mock progress forward for fixtures with a
  // `.progress` simulation. Cleaned up on fixture change.
  const progressTimerRef = useRef<number | null>(null);

  const sendToolResult = useCallback((target: Window, fx: Fixture) => {
    const message = {
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-result',
      params: {
        content: [{ type: 'text', text: fx.description ?? fx.name }],
        structuredContent: fx.structuredContent,
      },
    };
    console.debug('[workbench] → tool-result', fx.name, message.params);
    target.postMessage(message, '*');
    setStatus('pushed-result');
  }, []);

  const startMockProgress = useCallback((fx: Fixture) => {
    if (!fx.progress) return;
    const target = iframeRef.current?.contentWindow;
    if (!target) return;

    // Reset state to "starting".
    mockProgressRef.current = {
      kind: fx.progress.kind,
      current: 0,
      total: fx.progress.trackLabels.length,
      message: '',
      operation: fx.progress.operation,
      done: false,
    };
    setStatus('running-progress');

    const tickMs = fx.progress.tickMs ?? 700;
    const labels = fx.progress.trackLabels;
    const total = labels.length;
    const finalPayload = fx.progress.finalPayload;

    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
    }

    progressTimerRef.current = window.setInterval(() => {
      const next = mockProgressRef.current.current + 1;
      if (next > total) {
        // Bar full: mark done, fire the final tool-result, stop ticking.
        mockProgressRef.current = {
          ...mockProgressRef.current,
          current: total,
          done: true,
        };
        if (progressTimerRef.current) {
          window.clearInterval(progressTimerRef.current);
          progressTimerRef.current = null;
        }
        target.postMessage(
          {
            jsonrpc: '2.0',
            method: 'ui/notifications/tool-result',
            params: {
              content: [{ type: 'text', text: 'mock progress complete' }],
              structuredContent: finalPayload,
            },
          },
          '*'
        );
        setStatus('pushed-result');
        return;
      }
      mockProgressRef.current = {
        ...mockProgressRef.current,
        current: next,
        message: labels[next - 1] ?? '',
      };
    }, tickMs);
  }, []);

  useEffect(() => {
    function onMessage(ev: MessageEvent) {
      const msg = ev.data;
      const target = iframeRef.current?.contentWindow;
      if (!msg || msg.jsonrpc !== '2.0' || !target) return;
      // Vite HMR uses postMessage on the same window; filter to just
      // messages whose source is the iframe we're hosting.
      if (ev.source !== target) return;

      if (msg.method === 'ui/initialize' && msg.id != null) {
        console.debug('[workbench] ← ui/initialize', msg.params);
        target.postMessage(
          {
            jsonrpc: '2.0',
            id: msg.id,
            result: buildHostResponse(themeRef.current),
          },
          '*'
        );
        setStatus('awaiting-initialize');
        return;
      }
      if (msg.method === 'ui/notifications/initialized') {
        console.debug('[workbench] ← ui/notifications/initialized');
        initializedRef.current = true;
        setStatus('initialized');
        if (fixtureRef.current.progress) {
          // Live-progress fixture: run the mock sequence and fire
          // tool-result only when it finishes.
          startMockProgress(fixtureRef.current);
        } else {
          sendToolResult(target, fixtureRef.current);
        }
        return;
      }
      // Stand-in for the MCP server's `resources/read` handler. The
      // sync-result bundle's live-progress component polls this; we
      // respond with the mock state so the bar can advance in dev.
      if (msg.method === 'resources/read' && msg.id != null) {
        const uri = (msg.params as { uri?: string } | undefined)?.uri ?? '';
        if (uri === PROGRESS_URI) {
          target.postMessage(
            {
              jsonrpc: '2.0',
              id: msg.id,
              result: {
                contents: [
                  {
                    uri,
                    mimeType: 'application/json',
                    text: JSON.stringify(mockProgressRef.current),
                  },
                ],
              },
            },
            '*'
          );
          return;
        }
        // Unknown resource: respond with an empty contents array so
        // the SDK doesn't time out the request.
        target.postMessage(
          {
            jsonrpc: '2.0',
            id: msg.id,
            result: { contents: [] },
          },
          '*'
        );
        return;
      }
      if (msg.method?.startsWith('ui/')) {
        console.debug('[workbench] ←', msg.method, msg.params);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [sendToolResult, startMockProgress]);

  // Iframe (re)mount: clear initialized state so the next ui/initialize
  // round-trip pushes a fresh tool-result. Triggered on bundle change
  // (iframe src changes), on reloadKey bump, and on initial mount.
  useEffect(() => {
    initializedRef.current = false;
    setStatus('mounting');
    // Cancel any in-flight progress simulation; the new iframe will
    // start fresh when it re-handshakes.
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    mockProgressRef.current = idleProgress();
  }, [bundle, reloadKey]);

  // Fixture change without iframe remount: if the iframe is already
  // initialized, either push the new tool-result OR kick off a new
  // mock-progress sequence (and reset the iframe's payload first by
  // bumping reloadKey, so the bundle's Pending component re-mounts).
  useEffect(() => {
    if (!initializedRef.current) return;
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    if (fixture.progress) {
      // To re-show the Pending state for a new progress sim, we need
      // the bundle to forget its previous payload. Cleanest way: bump
      // the iframe's key so it remounts and re-handshakes.
      setReloadKey((k) => k + 1);
      return;
    }
    const target = iframeRef.current?.contentWindow;
    if (target) sendToolResult(target, fixture);
  }, [fixture, sendToolResult]);

  // Clean up the timer on unmount so we don't leak intervals.
  useEffect(() => {
    return () => {
      if (progressTimerRef.current) {
        window.clearInterval(progressTimerRef.current);
      }
    };
  }, []);

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '260px 1fr',
        height: '100vh',
        gap: 0,
      }}
    >
      <aside
        style={{
          padding: '16px 12px',
          borderRight: '1px solid light-dark(#e0e0e0, #2e2e2e)',
          overflowY: 'auto',
          fontSize: 13,
        }}
      >
        <h1 style={{ fontSize: 14, margin: '0 0 12px' }}>
          clickwheel workbench
        </h1>
        {bundles.map((b) => (
          <div key={b.slug} style={{ marginBottom: 16 }}>
            <button
              onClick={() => {
                setBundle(b);
                setFixture(b.fixtures[0]);
              }}
              style={{
                background: bundle.slug === b.slug ? '#3b82f6' : 'transparent',
                color: bundle.slug === b.slug ? '#fff' : 'inherit',
                border: '1px solid light-dark(#d4d4d4, #3a3a3a)',
                borderRadius: 4,
                padding: '6px 10px',
                width: '100%',
                textAlign: 'left',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {b.label}
            </button>
            {bundle.slug === b.slug && (
              <ul
                style={{
                  listStyle: 'none',
                  padding: 0,
                  margin: '8px 0 0 8px',
                }}
              >
                {b.fixtures.map((fx) => (
                  <li key={fx.name}>
                    <button
                      onClick={() => setFixture(fx)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        padding: '4px 0',
                        cursor: 'pointer',
                        textAlign: 'left',
                        color: fixture.name === fx.name ? '#3b82f6' : 'inherit',
                        fontWeight: fixture.name === fx.name ? 600 : 400,
                        fontSize: 12,
                      }}
                    >
                      {fx.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
        <button
          onClick={() => setReloadKey((k) => k + 1)}
          style={{
            marginTop: 8,
            padding: '4px 8px',
            fontSize: 12,
            cursor: 'pointer',
          }}
        >
          reload iframe
        </button>
        <div
          style={{
            marginTop: 16,
            fontSize: 11,
            opacity: 0.7,
            fontFamily: 'ui-monospace, monospace',
          }}
        >
          status: {status}
        </div>
      </aside>
      <main
        style={{
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <header
          style={{
            display: 'flex',
            gap: 16,
            alignItems: 'center',
            padding: '12px 24px',
            borderBottom:
              '1px solid light-dark(rgba(0,0,0,0.08), rgba(255,255,255,0.08))',
            fontSize: 12,
          }}
        >
          <ToggleGroup
            label="Viewport"
            options={[
              { value: 'mobile', label: 'Mobile' },
              { value: 'tablet', label: 'Tablet' },
              { value: 'desktop', label: 'Desktop' },
            ]}
            value={viewport}
            onChange={(v) => setViewport(v as Viewport)}
          />
          <ToggleGroup
            label="Theme"
            options={[
              { value: 'light', label: 'Light' },
              { value: 'dark', label: 'Dark' },
            ]}
            value={theme}
            onChange={(v) => setTheme(v as Theme)}
          />
        </header>
        <div
          style={{
            padding: 24,
            overflow: 'auto',
            flex: 1,
          }}
        >
          <iframe
            key={`${bundle.slug}-${reloadKey}`}
            ref={iframeRef}
            src={bundle.entryUrl}
            title={bundle.label}
            style={{
              display: 'block',
              width: '100%',
              maxWidth: VIEWPORT_WIDTHS[viewport],
              minHeight: 280,
              border: 'none',
              background: 'transparent',
              transition: 'max-width 200ms ease',
            }}
          />
          <details
            style={{
              marginTop: 16,
              fontSize: 12,
              opacity: 0.7,
              maxWidth: VIEWPORT_WIDTHS[viewport],
            }}
          >
            <summary>fixture payload</summary>
            <pre style={{ fontSize: 11, lineHeight: 1.4 }}>
              {JSON.stringify(fixture.structuredContent, null, 2)}
            </pre>
          </details>
        </div>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Workbench />
  </StrictMode>
);
