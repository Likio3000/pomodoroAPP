# Moving from Flask to version 2

This is a product and architecture replacement, not an in-place SQL migration. Do not point the new app at an existing database: it has no database server connection at all.

1. Keep a backup of the previous deployment and its database before changing hosting.
2. If people use the old accounts, export their session records through the existing authenticated interface before retiring it. Do not publish database files or user exports in this repository.
3. Test version 2 on a separate origin. Test data on that origin will remain separate from the final production origin.
4. Decide when to switch hosting. Version 2 has no login or shared leaderboard, and existing history will not appear automatically. Its JSON importer accepts only the documented version 2 schema, not arbitrary legacy exports.
5. Keep the old revision available for rollback. The complete prior application remains in Git history; the new source checkout removes its code and dependencies.

The rebuild and local preview do not change any deployed service or existing server-side database. The existing GitHub repository's default branch changes only when the rebuild branch is merged.

## Export format

The backup root contains `version: 2`, `settings`, `tasks` and `sessions`. Active timers are deliberately excluded, so importing a backup never silently starts a session or credits a partly finished one. Task IDs and session IDs must be unique; settings, text lengths, timestamps and durations are validated. Exports are personal data and should be stored accordingly.

Session durations are milliseconds, completion timestamps are Unix epoch milliseconds, and titles are plain text. The CSV export is suitable for inspection and analysis; JSON is the roundtrip backup format.
