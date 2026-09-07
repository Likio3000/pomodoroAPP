# pomodoro.

**Una cosa a la vez.** A quiet, local-first focus app with a Spanish interface. Plan a small task, give it your attention, take a break, and see where your time went.

Version 2 is a complete rebuild in React and TypeScript. It requires no account, server database, API key, analytics service, or model provider.

## Run it

Use Node.js 24 LTS and npm.

```sh
npm ci
npm run dev
```

Open the local address printed by Vite. To test the production build, including offline support:

```sh
npm run build
npm run preview
```

## What works

- Focus, short breaks and long breaks, with configurable durations. Every fourth completed focus offers a long break. The next session starts only when you choose.
- Pause, resume and reload recovery. A running timer is calculated from a persisted deadline, rather than by subtracting one every second.
- Tasks with selection, editing, completion and per-task session counts. A session retains its original task title even if the task is later edited or deleted.
- A daily goal, local-calendar streak, seven-day view and filterable session history. Only completed focus sessions contribute minutes. There is no seeded activity.
- A soft completion chime and optional browser notifications. The space bar starts and pauses the timer outside forms and dialogs.
- JSON backup/restore and CSV session export. Imports are validated before a separate confirmation replaces local data.
- Offline reopening after the production app has loaded successfully. The app shell is cached by a versioned service worker; private data remains in IndexedDB.
- Responsive layouts, keyboard navigation, labelled controls, native focus-trapping dialogs and reduced-motion support.

## Data and timer guarantees

The application stores one versioned record in IndexedDB. Each transition reads and writes that record inside one transaction. Concurrent tabs therefore serialize updates rather than replacing each other's stale copies. A finished timer's identifier is retained as the session identifier, and completion moves the timer to an idle next phase in the same transaction. Only the transaction that actually finishes a session emits its completion event.

BroadcastChannel updates other open tabs after a successful write. Returning to a tab also reconciles a due timer. Closing the app does not run a background process: on reopening, an elapsed focus is recorded once at its scheduled completion time. A chime or notification cannot be guaranteed while the browser is closed, sleeping, or suspending background activity.

Data is **local to this browser profile and origin**. Changing hostname, port or browser creates a different storage space. Clearing site data or using a private browsing session may remove history. Export a JSON copy to move devices or keep a backup. There is no cloud synchronization or recovery service. The app reports storage failures instead of silently accepting unsaved changes.

CSV uses ISO timestamps and escapes spreadsheet formulas. Display dates and streaks use the device's current timezone. A session belongs to the local date on which it ended, including sessions that cross midnight. Imported history is user-provided data; these statistics are a personal record, not a verified measurement of attention.

## Architecture

```text
src/domain/model.ts       Pure timer/task transitions and import validation
src/domain/database.ts    Atomic IndexedDB read/modify/write operations
src/domain/stats.ts       Local-day aggregation and CSV encoding
src/store.ts              React subscription, tab synchronization, completion
src/components/           Timer, tasks, progress, settings and dialog surfaces
src/styles.css            Responsive component styling
src/theme.css             Shared design tokens
scripts/service-worker.mjs  Build-time, content-versioned offline shell
tests/                    Domain, persistence and calendar/export checks
```

The runtime dependencies are React and React DOM. No AI integration, chat UI, speech generation, external fonts or third-party runtime requests are included.

## Validation

```sh
npm test          # Domain transitions, backup validation, concurrent persistence
npm run build    # Strict TypeScript checking and production bundle
npm run check    # Both checks; also runs in GitHub Actions
```

The persistence suite uses two IndexedDB connections to exercise simultaneous writes and completion. Timer tests advance explicit timestamps rather than waiting in real time. Calendar tests use local dates; running them with `TZ=Australia/Melbourne npm test` also covers a non-UTC environment.

Browser acceptance checklist:

1. Create and select a task, change focus to one minute, start and pause.
2. Reload; resume the same remaining time and finish the session.
3. Confirm exactly one history row, a proposed break and updated daily progress.
4. Open a second tab; confirm changes propagate and no duplicate completion appears.
5. Export and restore a backup, including rejecting malformed files.
6. Reload the production app offline after the service worker is ready.
7. Check desktop and narrow mobile layouts, keyboard focus, dialogs and accessible names.

Automated checks do not establish compatibility with every browser, operating system or assistive technology. Native notification delivery depends on browser permissions and platform support.

## Deploy

`npm run build` creates a static `dist/` directory. Serve it over HTTPS from a static host; localhost works for local development. Use hash navigation, so no server route rewrites are needed. The build uses relative asset paths and supports a subdirectory.

Serve `index.html` and `sw.js` with revalidation (`Cache-Control: no-cache`), and hashed assets with a long immutable cache lifetime. A new service worker becomes active after the previous app tabs close, avoiding forced reloads during a session. Use a stable origin to preserve local data.

No deployment is performed by the check workflow. See [migration notes](docs/migration.md) before replacing an existing Flask deployment.

## From the previous version

The Flask application is preserved in Git history. The rebuild intentionally removes accounts, server-side leaderboards, AI chat, generated speech, model SDKs, personas and key configuration. Existing server databases are not opened, modified or deleted by this app. Version 2 does not automatically import legacy accounts or history; keep a separate export before retiring a version 1 deployment.

Design direction and component rules: [design specification](docs/design.md). MIT licensed; see [LICENSE](LICENSE).
