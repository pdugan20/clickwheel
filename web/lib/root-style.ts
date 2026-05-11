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
  borderRadius: 12,
  border: `1px solid light-dark(${CARD_BORDER_LIGHT}, ${CARD_BORDER_DARK})`,
  boxSizing: 'border-box',
};
