/**
 * Fixtures for the workbench preview of the sync-result summary card.
 * Each fixture mirrors one of the three tool result shapes the bundle
 * can receive.
 */
import type { Fixture } from './ipod-capacity.fixtures.js';

export const fixtures: Fixture[] = [
  {
    name: 'sync_playlist · happy path',
    description: '5 tracks copied, iPod-side playlist created.',
    structuredContent: {
      synced: true,
      playlist: 'test-mix',
      ipod_playlist: 'test-mix',
      on_conflict: null,
      added: 5,
      failed: 0,
      also_on_ipod: 0,
      library_updated: true,
    },
  },
  {
    name: 'sync_playlist · already in sync',
    description: 'No-op sync — playlist already matches the iPod.',
    structuredContent: {
      synced: false,
      playlist: 'test-mix',
    },
  },
  {
    name: 'sync_playlist · conflict (pre-resolution)',
    description: 'Same-name playlist exists; user picks merge/replace/rename.',
    structuredContent: {
      synced: false,
      playlist: 'test-mix',
      conflict: {
        existing_name: 'test-mix',
        existing_track_count: 3,
        message: "An iPod playlist named 'test-mix' already exists.",
      },
    },
  },
  {
    name: 'sync_playlist · merged',
    description: 'Conflict resolved with merge; one new track added.',
    structuredContent: {
      synced: true,
      playlist: 'test-mix',
      ipod_playlist: 'test-mix',
      on_conflict: 'merge',
      added: 1,
      failed: 0,
      also_on_ipod: 0,
      library_updated: true,
    },
  },
  {
    name: 'sync_playlist · renamed',
    description: 'Conflict resolved with rename to test-mix-v2.',
    structuredContent: {
      synced: true,
      playlist: 'test-mix',
      ipod_playlist: 'test-mix-v2',
      on_conflict: 'rename',
      added: 0,
      failed: 0,
      also_on_ipod: 0,
      library_updated: true,
    },
  },
  {
    name: 'add_tracks · big batch',
    description: 'Realistic 33-track Black Keys discography add.',
    structuredContent: {
      added: 33,
      failed: 0,
      already_present: 0,
      library_updated: true,
    },
  },
  {
    name: 'add_tracks · all already present',
    description: 'Idempotent re-add — nothing new copied.',
    structuredContent: {
      added: 0,
      failed: 0,
      already_present: 5,
      library_updated: true,
    },
  },
  {
    name: 'add_artist · happy path',
    description: 'Push all of Wilco — 124 tracks, 2 failed.',
    structuredContent: {
      artist: 'Wilco',
      added: 122,
      failed: 2,
      already_present: 0,
      found_in_library: 124,
      library_updated: true,
    },
  },
  {
    name: 'add_artist · library not updated',
    description: 'Tracks copied but iTunesDB write failed (degraded).',
    structuredContent: {
      artist: 'Wilco',
      added: 124,
      failed: 0,
      already_present: 0,
      found_in_library: 124,
      library_updated: false,
    },
  },
];
