/**
 * Fixtures for the workbench preview of the sync-result summary card.
 * Each fixture mirrors one of the three tool result shapes the bundle
 * can receive.
 */
import type { Fixture } from './ipod-capacity.fixtures.js';

export const fixtures: Fixture[] = [
  {
    name: 'live progress · 33-track add',
    description:
      "Plays back a mock sync-progress sequence (workbench responds to the bundle's resources/read polls) so you can preview the live progress bar without a real iPod. Switches to the final summary after the bar fills.",
    structuredContent: {} as Record<string, never>,
    progress: {
      kind: 'add',
      operation: '33 tracks',
      tickMs: 700,
      trackLabels: [
        'The Black Keys — Thickfreakness',
        'The Black Keys — Hard Row',
        'The Black Keys — Set You Free',
        'The Black Keys — Midnight in Her Eyes',
        'The Black Keys — Have Love Will Travel',
        'The Black Keys — Hurt Like Mine',
        'The Black Keys — Everywhere I Go',
        'The Black Keys — No Trust',
        'The Black Keys — If You See Me',
        'The Black Keys — Hold Me in Your Arms',
        'The Black Keys — I Cry Alone',
        'The Black Keys — 10 A.M. Automatic',
        'The Black Keys — All Hands Against His Own',
        'The Black Keys — When the Lights Go Out',
        'The Black Keys — Same Old Thing',
        'The Black Keys — Aeroplane Blues',
        'The Black Keys — Strange Desire',
        'The Black Keys — The Lengths',
        'The Black Keys — Grown So Ugly',
        'The Black Keys — Stack Shot Billy',
        'The Black Keys — Modern Times',
        "The Black Keys — Just Couldn't Tie Me Down",
        'The Black Keys — Girl Is on My Mind',
        'The Black Keys — Your Touch',
        "The Black Keys — You're the One",
        'The Black Keys — Goodbye Babylon',
        'The Black Keys — Black Door',
        'The Black Keys — Magic Potion',
        'The Black Keys — Just Got to Be',
        'The Black Keys — Tighten Up',
        "The Black Keys — Howlin' for You",
        "The Black Keys — She's Long Gone",
        'The Black Keys — Lonely Boy',
      ],
      finalPayload: {
        added: 33,
        failed: 0,
        already_present: 0,
        library_updated: true,
      },
    },
  },
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
  {
    name: 'remove_tracks · happy path',
    description: '5 Pinkerton tracks dropped — ~24 MB freed.',
    structuredContent: {
      removed: 5,
      not_matched: 0,
      bytes_freed: 23_900_000,
      library_updated: true,
    },
  },
  {
    name: 'remove_tracks · partial match',
    description: 'Some paths not on iPod — reported as not_matched.',
    structuredContent: {
      removed: 3,
      not_matched: 2,
      bytes_freed: 14_400_000,
      library_updated: true,
    },
  },
  {
    name: 'remove_artist · clean sweep',
    description: 'Remove all Taylor Swift — 255 tracks gone.',
    structuredContent: {
      artist: 'Taylor Swift',
      removed: 255,
      bytes_freed: 1_350_000_000,
      library_updated: true,
    },
  },
  {
    name: 'remove_ipod_playlist · success',
    description: 'Drop a playlist artifact; underlying tracks preserved.',
    structuredContent: {
      ipod_playlist: 'workout',
      removed_playlist: true,
      library_updated: true,
    },
  },
];
