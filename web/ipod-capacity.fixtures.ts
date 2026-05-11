/**
 * Fixtures for the workbench. Each fixture is a synthetic
 * `structuredContent` payload that the workbench posts to the iframe so
 * the bundle renders against realistic data without a live iPod.
 */

export type Fixture = {
  name: string;
  description?: string;
  /** Mirrors what get_ipod_contents returns from the MCP server. */
  structuredContent: Record<string, unknown>;
};

// Fixtures mirror what get_ipod_contents returns. The server rolls up
// `top_artists` via actions.primary_artist(), which prefers the
// per-track `album_artist` tag over `artist` — so collab variants like
// "Taylor Swift / HAIM" or "Taylor Swift, Ed Sheeran" never reach the
// bundle. They fold into the lead artist's count (whose album_artist
// is just "Taylor Swift") server-side.
export const fixtures: Fixture[] = [
  {
    name: 'classic — pop trio',
    description: '5th-gen iPod, mostly empty, three artists dominating.',
    structuredContent: {
      capacity_bytes: 63_790_000_000,
      used_bytes: 5_700_000_000,
      free_bytes: 58_090_000_000,
      track_count: 345,
      artist_count: 4,
      album_count: 24,
      top_artists: [
        // 240 + 6 + 4 + 3 + 2 collab tracks all roll under Taylor Swift.
        { artist: 'Taylor Swift', track_count: 255 },
        { artist: 'Sabrina Carpenter', track_count: 57 },
        { artist: 'Olivia Rodrigo', track_count: 23 },
        { artist: 'Weezer', track_count: 10 },
      ],
    },
  },
  {
    name: 'nearly full — long tail',
    description: 'A 30 GB iPod with a wide library — most segments thin.',
    structuredContent: {
      capacity_bytes: 29_800_000_000,
      used_bytes: 28_400_000_000,
      free_bytes: 1_400_000_000,
      track_count: 6_812,
      artist_count: 412,
      album_count: 1_204,
      top_artists: [
        { artist: 'The Beatles', track_count: 312 },
        { artist: 'Radiohead', track_count: 187 },
        { artist: 'Bob Dylan', track_count: 154 },
        { artist: 'Wilco', track_count: 121 },
        { artist: 'Joni Mitchell', track_count: 98 },
        { artist: 'Big Thief', track_count: 76 },
        { artist: 'Fleet Foxes', track_count: 54 },
        { artist: 'Vampire Weekend', track_count: 41 },
        { artist: 'Phoebe Bridgers', track_count: 39 },
        { artist: 'The National', track_count: 33 },
      ],
    },
  },
  {
    name: 'empty — fresh format',
    description: 'Edge case: just-formatted iPod, no tracks.',
    structuredContent: {
      capacity_bytes: 63_790_000_000,
      used_bytes: 0,
      free_bytes: 63_790_000_000,
      track_count: 0,
      artist_count: 0,
      album_count: 0,
      top_artists: [],
    },
  },
];
