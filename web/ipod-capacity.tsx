/**
 * Entry for the iPod-capacity bundle. Mirrors rewind's per-view entry
 * pattern: useApp() to handshake with the host, ontoolresult to receive
 * the structuredContent, render the relevant component below.
 */
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useApp } from '@modelcontextprotocol/ext-apps/react';
import { CapacityBar, type CapacityArtist } from './components/CapacityBar.js';
import { rootStyle } from './lib/root-style.js';

type IpodContents = {
  capacity_bytes: number;
  used_bytes: number;
  free_bytes: number;
  track_count: number;
  artist_count: number;
  album_count: number;
  top_artists: CapacityArtist[];
};

function IpodCapacityApp() {
  const { app, isConnected, error } = useApp({
    appInfo: { name: 'clickwheel-ipod-capacity', version: '0.1.0' },
    capabilities: {},
  });

  const [payload, setPayload] = useState<IpodContents | null>(null);

  useEffect(() => {
    if (!app) return;
    app.ontoolresult = (result) => {
      const sc = result?.structuredContent as IpodContents | undefined;
      if (sc?.capacity_bytes != null) setPayload(sc);
    };
  }, [app]);

  if (error) {
    return <div style={rootStyle}>Error: {error.message}</div>;
  }
  if (!isConnected) return null;
  if (payload === null) {
    return <div style={rootStyle}>Waiting for iPod data…</div>;
  }

  return (
    <div style={rootStyle}>
      <CapacityBar
        capacity_bytes={payload.capacity_bytes}
        used_bytes={payload.used_bytes}
        free_bytes={payload.free_bytes}
        top_artists={payload.top_artists}
      />
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <IpodCapacityApp />
  </StrictMode>
);
