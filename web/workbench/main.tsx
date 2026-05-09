/**
 * Local design workbench for clickwheel MCP Apps bundles.
 *
 * Mounts the production bundle's HTML entry inside an iframe and plays
 * the host side of the MCP Apps protocol against it: responds to the
 * `ui/initialize` request with a stub host context, accepts `size-changed`
 * notifications, and pushes a fake `ui/notifications/tool-result` carrying
 * the selected fixture's structuredContent.
 *
 * This exercises the same connect/handshake/render path that Claude
 * Desktop will use, just with manual fixture data instead of a real
 * tool call. Iterate on components in `web/components/`, save, and
 * Vite's HMR re-mounts the bundle automatically.
 */
import { StrictMode, useEffect, useMemo, useRef, useState } from 'react';
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

type Connection = {
  initialized: boolean;
  pendingFixture: Fixture | null;
};

function Workbench() {
  const [bundle, setBundle] = useState<Bundle>(bundles[0]);
  const [fixture, setFixture] = useState<Fixture>(bundles[0].fixtures[0]);
  const [reloadKey, setReloadKey] = useState(0);

  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const connRef = useRef<Connection>({
    initialized: false,
    pendingFixture: null,
  });

  const sendToolResult = useMemo(
    () => (target: Window, fx: Fixture) => {
      target.postMessage(
        {
          jsonrpc: '2.0',
          method: 'ui/notifications/tool-result',
          params: {
            content: [{ type: 'text', text: fx.description ?? fx.name }],
            structuredContent: fx.structuredContent,
          },
        },
        '*'
      );
    },
    []
  );

  useEffect(() => {
    function onMessage(ev: MessageEvent) {
      const msg = ev.data;
      const target = iframeRef.current?.contentWindow;
      if (!msg || msg.jsonrpc !== '2.0' || !target) return;
      if (ev.source !== target) return;

      if (msg.method === 'ui/initialize' && msg.id != null) {
        target.postMessage(
          { jsonrpc: '2.0', id: msg.id, result: HOST_RESPONSE },
          '*'
        );
        return;
      }
      if (msg.method === 'ui/notifications/initialized') {
        connRef.current.initialized = true;
        if (connRef.current.pendingFixture) {
          sendToolResult(target, connRef.current.pendingFixture);
          connRef.current.pendingFixture = null;
        }
        return;
      }
      // size-changed and other notifications: log for visibility, no-op.
      if (msg.method?.startsWith('ui/')) {
        console.debug('[workbench] iframe →', msg.method, msg.params);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [sendToolResult]);

  // When the user picks a bundle/fixture (or hits reload), queue the
  // fixture and let the iframe finish its handshake before pushing it.
  useEffect(() => {
    connRef.current = { initialized: false, pendingFixture: fixture };
  }, [bundle, fixture, reloadKey]);

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
