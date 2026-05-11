/**
 * Single fixture for the stats-treatment showcase. Same shape as the
 * real library-stats bundle so all three variants render real-looking
 * data.
 */
import type { Fixture } from './ipod-capacity.fixtures.js';

export const fixtures: Fixture[] = [
  {
    name: 'medium library',
    description: 'All three stat-grid treatments stacked for comparison.',
    structuredContent: {
      stats: {
        total_tracks: 5_124,
        artists: 312,
        albums: 678,
        total_bytes: 32_500_000_000,
        total_seconds: 1_240_000,
        with_art: 4_812,
        without_art: 312,
        missing_genre: 41,
        missing_title: 0,
        missing_artist: 2,
      },
      formats: [
        { format: 'mp3', count: 3_812, total_bytes: 22_400_000_000 },
        { format: 'm4a', count: 982, total_bytes: 6_900_000_000 },
        { format: 'flac', count: 287, total_bytes: 2_900_000_000 },
        { format: 'alac', count: 43, total_bytes: 280_000_000 },
      ],
    },
  },
];
