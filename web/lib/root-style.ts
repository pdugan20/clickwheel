/**
 * Shared inline style for the outermost <div> of every bundle. Mirrors
 * rewind's root-style.ts: lets host theme tokens flow through and keeps
 * each bundle visually consistent without a CSS framework.
 */
import type { CSSProperties } from 'react';

export const rootStyle: CSSProperties = {
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  fontSize: 13,
  lineHeight: 1.4,
  color: 'var(--color-text-primary, light-dark(#1a1a1a, #f0f0f0))',
  background: 'var(--color-background-primary, light-dark(#fafafa, #1a1a1a))',
  padding: 16,
  borderRadius: 'var(--border-radius-md, 8px)',
  boxSizing: 'border-box',
};
