/**
 * Shared inline style for the outermost <div> of every bundle. Mirrors
 * rewind's card chrome (see rewind/mcp-server/web/lib/colors.mjs +
 * card-tokens.ts): a literal cream/off-white card with a visible gray
 * border, not the opacity-faded border Claude Desktop's
 * --color-border-* variables collapse to.
 *
 * We hard-code the hex values rather than chaining through host-injected
 * CSS variables because Claude Desktop's injected --color-border-* are
 * barely-there alpha values, and we want the visible card edge that
 * Rewind's iPad / Desktop layout uses.
 */
import type { CSSProperties } from 'react';

// Card chrome — matches rewind/mcp-server/web/lib/colors.mjs verbatim.
const CARD_BG_LIGHT = '#fcfcfa';
const CARD_BG_DARK = '#272726';
const CARD_BORDER_LIGHT = '#d9d9d9';
const CARD_BORDER_DARK = '#383836';

// Anthropic brand blue. Used for the live-progress bar and any other
// "accent" callout. Kept here so all bundles pull from one source.
export const BRAND_BLUE = '#336ECB';

// On iOS, Claude wraps the card iframe in its OWN rounded WKWebView
// container. If we also round + border the card, the two masks fight at the
// corners and ours get clipped square (and the border leaves a hairline gap
// against the host mask). So on iOS we go edge-to-edge — no radius, no border
// — and let the host's container be the only thing rounding the corners.
// (Same fix rewind + bibliocommons MCP servers use.) Everywhere else — the
// workbench (host browser) and Claude Desktop (Electron), neither of which
// wraps us in an outer rounded container — keep our own 12px chrome.
//
// Detection uses three signals because Claude iOS's WKWebView may send a UA
// string without "iPhone/iPad/iPod": `'standalone' in navigator` exists only
// on iOS Safari/WKWebView (survives UA spoofing); the UA regex catches stock
// iOS; and the Macintosh-UA + touch-points check catches iPads that report as
// desktop Mac. Claude Desktop's Electron Chromium matches none of the three.
function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent;
  return (
    'standalone' in navigator ||
    /iPad|iPhone|iPod/.test(ua) ||
    (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
  );
}

const ON_IOS = isIOS();

export const rootStyle: CSSProperties = {
  fontFamily:
    'var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif)',
  fontSize: 13,
  lineHeight: 1.4,
  color: 'var(--color-text-primary, light-dark(#1a1a1a, #f0f0f0))',
  background: `light-dark(${CARD_BG_LIGHT}, ${CARD_BG_DARK})`,
  // Asymmetric on purpose. The h2 title's line-box has ~3-4px of
  // leading above its glyph cap-height, so a symmetric 20px on top
  // and bottom *reads* as ~23px top / 20px bottom. Trim the top to
  // compensate so the visual gap matches.
  padding: '16px 20px 20px 20px',
  borderRadius: ON_IOS ? 0 : 12,
  border: ON_IOS
    ? 'none'
    : `1px solid light-dark(${CARD_BORDER_LIGHT}, ${CARD_BORDER_DARK})`,
  boxSizing: 'border-box',
};

// Kill iOS WebKit's default gray rectangular tap-highlight on every
// interactive element in the bundle. It ignores border-radius and flashes an
// ugly dark rectangle when you tap the capacity card's clickable artist pills
// (a real <button>). Replace it with a subtle :active background tint so a
// tap still registers as touch feedback. (Same mobile polish rewind +
// bibliocommons ship alongside the iOS corner fix.)
//
// Injected once as a <style> in the bundle's own <head>. Each bundle runs in
// its own iframe in production, and the workbench mounts the built HTML entry
// inside an iframe too, so `document` is always the bundle's document — the
// right target in both. The id guard makes re-injection (StrictMode double
// mount, hot reload) a no-op.
const GLOBAL_CHROME_STYLE_ID = 'clickwheel-global-chrome';
const GLOBAL_CHROME_CSS = `
* { -webkit-tap-highlight-color: transparent; }
button:active, [role='button']:active, a:active {
  background-color: rgba(127, 127, 127, 0.08);
}
`;
if (
  typeof document !== 'undefined' &&
  !document.getElementById(GLOBAL_CHROME_STYLE_ID)
) {
  const style = document.createElement('style');
  style.id = GLOBAL_CHROME_STYLE_ID;
  style.textContent = GLOBAL_CHROME_CSS;
  document.head.appendChild(style);
}
