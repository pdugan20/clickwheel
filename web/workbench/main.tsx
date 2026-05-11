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

const HOST_RESPONSE = {
  protocolVersion: PROTOCOL_VERSION,
  hostInfo: { name: 'clickwheel-workbench', version: '0.1.0' },
  hostCapabilities: {
    openLinks: {},
    logging: {},
    sandbox: {},
  },
  hostContext: {
    theme: matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light',
    platform: 'desktop',
    locale: navigator.language,
  },
};

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

function Workbench() {
  const [bundle, setBundle] = useState<Bundle>(bundles[0]);
  const [fixture, setFixture] = useState<Fixture>(bundles[0].fixtures[0]);
  const [reloadKey, setReloadKey] = useState(0);
  const [status, setStatus] = useState<Status>('mounting');

  const iframeRef = useRef<HTMLIFrameElement | null>(null);

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
          { jsonrpc: '2.0', id: msg.id, result: HOST_RESPONSE },
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
      <main style={{ padding: 24, overflow: 'auto' }}>
        <div
          style={{
            border: '1px solid light-dark(#e0e0e0, #2e2e2e)',
            borderRadius: 8,
            background: 'light-dark(#fafafa, #1a1a1a)',
            padding: 16,
            maxWidth: 720,
          }}
        >
          <iframe
            key={`${bundle.slug}-${reloadKey}`}
            ref={iframeRef}
            src={bundle.entryUrl}
            title={bundle.label}
            style={{
              width: '100%',
              minHeight: 280,
              border: 'none',
              background: 'transparent',
            }}
          />
        </div>
        <details style={{ marginTop: 16, fontSize: 12, opacity: 0.7 }}>
          <summary>fixture payload</summary>
          <pre style={{ fontSize: 11, lineHeight: 1.4 }}>
            {JSON.stringify(fixture.structuredContent, null, 2)}
          </pre>
        </details>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Workbench />
  </StrictMode>
);
