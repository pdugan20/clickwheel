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

// Categorical 5-stop used by the iPod capacity bar. Selected from the
// workbench palette-showcase for max perceptual distance with just five
// hues (Coolors "balanced 5"): bubblegum pink, golden pollen, emerald,
// ocean blue, dark teal. The CapacityBar caps named-artist segments at
// this palette's length so colors never wrap and duplicate.
export const CAPACITY_PALETTE: readonly string[] = [
  '#EF476F',
  '#FFD166',
  '#06D6A0',
  '#118AB2',
  '#073B4C',
];
