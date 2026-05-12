/**
 * Bundle registry. Add a new entry per `web/<name>.tsx` bundle so the
 * workbench sidebar lists it and can mount it with its fixtures.
 *
 * `entryUrl` is what the workbench's iframe `src` points at. In dev mode
 * Vite serves `web/<name>.html` directly from the parent root — the
 * workbench config's `root` is the `web/` parent so these paths resolve.
 */
import {
  fixtures as ipodCapacityFixtures,
  type Fixture,
} from '../ipod-capacity.fixtures.js';
import { fixtures as libraryStatsFixtures } from '../library-stats.fixtures.js';
import { fixtures as syncResultFixtures } from '../sync-result.fixtures.js';

export type Bundle = {
  /** Slug shown in the sidebar and used as the URL hash. */
  slug: string;
  /** Human-readable label. */
  label: string;
  /** Path Vite serves the bundle's HTML entry from (relative to web/). */
  entryUrl: string;
  /** Available fixtures the workbench can post into the iframe. */
  fixtures: Fixture[];
};

export const bundles: Bundle[] = [
  {
    slug: 'ipod-capacity',
    label: 'iPod capacity',
    entryUrl: '/ipod-capacity.html',
    fixtures: ipodCapacityFixtures,
  },
  {
    slug: 'library-stats',
    label: 'Library overview',
    entryUrl: '/library-stats.html',
    fixtures: libraryStatsFixtures,
  },
  {
    slug: 'sync-result',
    label: 'Sync result',
    entryUrl: '/sync-result.html',
    fixtures: syncResultFixtures,
  },
];
