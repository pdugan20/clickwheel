/**
 * Fixtures for the library-stats workbench preview.
 */
import type { Fixture } from './ipod-capacity.fixtures.js';

export const fixtures: Fixture[] = [
  {
    name: 'medium library',
    description: '~5,000 tracks, mostly mp3, healthy artwork coverage.',
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
  {
    name: 'small fresh library',
    description: 'A few hundred tracks, single format.',
    structuredContent: {
      stats: {
        total_tracks: 287,
        artists: 24,
        albums: 38,
        total_bytes: 1_800_000_000,
        total_seconds: 64_000,
        with_art: 280,
        without_art: 7,
        missing_genre: 0,
        missing_title: 0,
        missing_artist: 0,
      },
      formats: [{ format: 'm4a', count: 287, total_bytes: 1_800_000_000 }],
    },
  },
  {
    name: 'patchy metadata',
    description: 'Library with low artwork coverage and missing tags.',
    structuredContent: {
      stats: {
        total_tracks: 2_104,
        artists: 188,
        albums: 312,
        total_bytes: 11_200_000_000,
        total_seconds: 480_000,
        with_art: 1_204,
        without_art: 900,
        missing_genre: 412,
        missing_title: 18,
        missing_artist: 24,
      },
      formats: [
        { format: 'mp3', count: 1_842, total_bytes: 9_400_000_000 },
        { format: 'm4a', count: 222, total_bytes: 1_400_000_000 },
        { format: 'flac', count: 40, total_bytes: 400_000_000 },
      ],
    },
  },
  {
    name: 'empty',
    description: 'Library hasn’t been scanned yet.',
    structuredContent: {
      stats: {
        total_tracks: 0,
        artists: 0,
        albums: 0,
        total_bytes: 0,
        total_seconds: 0,
        with_art: 0,
        without_art: 0,
        missing_genre: 0,
        missing_title: 0,
        missing_artist: 0,
      },
      formats: [],
    },
  },
];
