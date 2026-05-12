/**
 * Workbench-only fixture for the capacity-bar palette comparison view.
 * Mirrors the shape of `get_ipod_contents`'s structuredContent but the
 * bundle just uses `top_artists` to render five variants of the same
 * bar with different categorical palettes.
 */
import type { Fixture } from './ipod-capacity.fixtures.js';

export const fixtures: Fixture[] = [
  {
    name: 'realistic 7-artist iPod',
    description: 'Mock payload matching a real-ish iPod top_artists list.',
    structuredContent: {
      capacity_bytes: 60_000_000_000,
      used_bytes: 5_900_000_000,
      free_bytes: 54_100_000_000,
      track_count: 428,
      artist_count: 7,
      album_count: 22,
      top_artists: [
        { artist: 'Taylor Swift', track_count: 254 },
        { artist: 'Sabrina Carpenter', track_count: 58 },
        { artist: 'The Black Keys', track_count: 46 },
        { artist: 'Weezer', track_count: 33 },
        { artist: 'Olivia Rodrigo', track_count: 23 },
        { artist: 'Bob Dylan', track_count: 9 },
        { artist: 'Wilco', track_count: 5 },
      ],
    },
  },
];
