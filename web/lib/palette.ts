/**
 * Shared color palettes for clickwheel bundles. Decided through the
 * stats-showcase iteration: monochromatic Focus blue from dark → light
 * is the chosen direction for stacked-format / category bars.
 *
 * First entry is the "largest segment" tone — paint the dominant
 * category in the strongest shade so the eye sees mass first.
 */

// Mono Focus blue. Built around Anthropic's brand Focus #61AAF2; the
// dark step is a custom darkening so the dominant segment carries
// enough weight, and lighter steps fade to near-white for long tails.
export const MONO_BLUE: readonly string[] = [
  '#2C6FB8', // dark
  '#61AAF2', // focus
  '#8FC2F4',
  '#B7D7F7',
  '#D4E6FA',
  '#E5F0FC',
  '#F1F7FE',
];
