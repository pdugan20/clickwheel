/**
 * Fixtures for the library-health workbench preview.
 */
import type { Fixture } from './ipod-capacity.fixtures.js';

const now = Math.floor(Date.now() / 1000);

export const fixtures: Fixture[] = [
  {
    name: 'healthy',
    description: 'Recent scan, all files present, auto-scan on.',
    structuredContent: {
      library_dir: '/Users/me/Music/Library',
      library_dir_exists: true,
      total_tracks: 5_124,
      missing_tracks: 0,
      last_scan_at: now - 3600 * 2,
      auto_scan_enabled: true,
    },
  },
  {
    name: 'stale scan',
    description: 'Library was scanned weeks ago — should warn.',
    structuredContent: {
      library_dir: '/Users/me/Music/Library',
      library_dir_exists: true,
      total_tracks: 4_812,
      missing_tracks: 0,
      last_scan_at: now - 3600 * 24 * 32,
      auto_scan_enabled: false,
    },
  },
  {
    name: 'missing files',
    description: 'Some tracks in the index no longer exist on disk.',
    structuredContent: {
      library_dir: '/Volumes/Music/Library',
      library_dir_exists: true,
      total_tracks: 2_104,
      missing_tracks: 84,
      last_scan_at: now - 3600 * 6,
      auto_scan_enabled: true,
    },
  },
  {
    name: 'unmounted share',
    description: 'Music folder unreachable — typical SMB share offline.',
    structuredContent: {
      library_dir: '/Volumes/MusicNAS',
      library_dir_exists: false,
      total_tracks: 12_400,
      missing_tracks: 0,
      last_scan_at: now - 3600 * 48,
      auto_scan_enabled: true,
    },
  },
  {
    name: 'never scanned',
    description: 'Fresh install — no scan has run yet.',
    structuredContent: {
      library_dir: '/Users/me/Music/Library',
      library_dir_exists: true,
      total_tracks: 0,
      missing_tracks: 0,
      last_scan_at: null,
      auto_scan_enabled: false,
    },
  },
];
