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

// ---------------------------------------------------------------------------
// Categorical palettes for the iPod capacity bar.
//
// `CAPACITY_PALETTE` is the production default (passed by
// ipod-capacity.tsx). The CapacityBar component caps named-artist
// segments at the palette's length so colors never wrap and duplicate
// — excess artists roll into a single gray "Other" stripe.
//
// The rest are alternatives we explored in the workbench showcase
// before settling on Balanced 5. Kept here as named exports so we can
// swap one in by changing a single import, without having to look up
// hex codes again.
// ---------------------------------------------------------------------------

/** Production default. "Balanced 5" from Coolors — bubblegum pink, golden
 *  pollen, emerald, ocean blue, dark teal. Broad hue spread, max
 *  perceptual distance with just five colors. */
export const CAPACITY_PALETTE: readonly string[] = [
  '#EF476F',
  '#FFD166',
  '#06D6A0',
  '#118AB2',
  '#073B4C',
];

/** Tableau 10 — classic high-contrast categorical workhorse. */
export const TABLEAU_10: readonly string[] = [
  '#4E79A7',
  '#F28E2B',
  '#E15759',
  '#76B7B2',
  '#59A14F',
  '#EDC948',
  '#B07AA1',
  '#FF9DA7',
];

/** Okabe-Ito — designed for color-vision deficiency (Okabe & Ito 2008).
 *  The scientific gold standard for colorblind-safe categorical data. */
export const OKABE_ITO: readonly string[] = [
  '#E69F00',
  '#56B4E9',
  '#009E73',
  '#F0E442',
  '#0072B2',
  '#D55E00',
  '#CC79A7',
  '#999999',
];

/** Tol Bright — Paul Tol's colorblind-safe palette, more saturated than
 *  Okabe-Ito. 7 hues. */
export const TOL_BRIGHT: readonly string[] = [
  '#4477AA',
  '#EE6677',
  '#228833',
  '#CCBB44',
  '#66CCEE',
  '#AA3377',
  '#BBBBBB',
];

/** Anthropic-brand warm — Book Cloth, Kraft, Manilla, Focus blue,
 *  cloud grays. Earth tones for an on-brand vibe. */
export const ANTHROPIC_WARM: readonly string[] = [
  '#CC785C',
  '#D4A27F',
  '#EBDBBC',
  '#61AAF2',
  '#91918D',
  '#666663',
  '#BFBFBA',
  '#E5E4DF',
];

/** Single-hue progression from raspberry through indigo to sky aqua.
 *  Reads like a gradient — vibey, not strictly categorical. */
export const MAGENTA_TO_AQUA: readonly string[] = [
  '#B5179E',
  '#7209B7',
  '#560BAD',
  '#480CA8',
  '#3A0CA3',
  '#3F37C9',
  '#4361EE',
  '#4895EF',
  '#4CC9F0',
];

/** Punchy pastels — blush, apricot, cream, tea green, aqua, baby blue,
 *  periwinkle, mauve. Soft but readable. */
export const PASTEL_RAINBOW: readonly string[] = [
  '#FFADAD',
  '#FFD6A5',
  '#FDFFB6',
  '#CAFFBF',
  '#9BF6FF',
  '#A0C4FF',
  '#BDB2FF',
  '#FFC6FF',
];

/** Saturated 5-stop: navy, dark raspberry, hot fuchsia, blaze orange,
 *  amber gold. Bold sunset. Wraps for >5 segments. */
export const SUNSET_BOLD: readonly string[] = [
  '#390099',
  '#9E0059',
  '#FF0054',
  '#FF5400',
  '#FFBD00',
];

/** Amber, blaze orange, neon pink, blue-violet, azure. Cleaner hue
 *  separation than SUNSET_BOLD. Wraps for >5 segments. */
export const VIBRANT_5: readonly string[] = [
  '#FFBE0B',
  '#FB5607',
  '#FF006E',
  '#8338EC',
  '#3A86FF',
];
