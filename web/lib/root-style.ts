/**
 * Shared inline style for the outermost <div> of every bundle. Mirrors
 * rewind's root-style.ts: lets host theme tokens flow through and keeps
 * each bundle visually consistent without a CSS framework.
 *
 * The card treatment (subtle border + slightly contrasting background +
 * generous padding) makes the bundle read as its own surface inside the
 * chat rather than blending into the message body.
 */
import type { CSSProperties } from 'react';

// Anthropic brand blue. Used for the live-progress bar and any other
// "accent" callout. Kept here so all bundles pull from one source.
export const BRAND_BLUE = '#336ECB';

export const rootStyle: CSSProperties = {
  fontFamily:
    'var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif)',
  fontSize: 13,
  lineHeight: 1.4,
  color: 'var(--color-text-primary, light-dark(#1a1a1a, #f0f0f0))',
  background: 'var(--color-background-secondary, light-dark(#fbfaf7, #232323))',
  padding: 20,
  borderRadius: 'var(--border-radius-lg, 12px)',
  border:
    '1px solid var(--color-border-secondary, light-dark(rgba(0, 0, 0, 0.08), rgba(255, 255, 255, 0.08)))',
  boxSizing: 'border-box',
};
