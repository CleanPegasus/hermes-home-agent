# Hermes Upgrade Runbook

Use this ritual whenever the upstream Hermes agent, the MCP package, or a custom skill changes. The goal is to make upgrades boring: record the version, run the same golden commands, compare the resulting pages and state changes, then promote or roll back.

## Version Record

Before changing anything, capture:

- Current Hermes source or package version.
- Current `hermes-home-mcp` version.
- Current custom skill directory checksum or commit.
- Current server and web commit or release tag.
- Database schema version or migration id.

Suggested note format:

```text
date:
operator:
hermes_version_before:
hermes_version_after:
mcp_version:
skills_version:
server_version:
web_version:
database_schema:
result:
rollback_plan:
```

## Upgrade Steps

1. Create a fresh branch or deployment candidate.
2. Update Hermes, MCP package metadata, or skill files.
3. Install dependencies in the same way production will install them.
4. Start a clean local database from `db/schema.sql`.
5. Run the golden commands below with `AGENT_CMD` pointed at the candidate Hermes command.
6. Review generated pages for action buttons, sanitization, and usefulness.
7. Review Vikunja tasks plus Hermes cache rows for todos, notes, tiles, approvals, pages, jobs, and job events.
8. Promote only if the golden command checklist passes.

## Golden Commands

Run each command through `POST /api/command`, then inspect `/api/jobs/{id}`, `/api/jobs/{id}/events`, `/api/pages/{page_id}`, and the affected collection route.

```text
add buy oat milk to my todos
make a note that the hallway filter size is 20x25x1
summarize my open todos as a page
schedule dentist checkup next Tuesday at 4pm
```

Expected results:

- Todo command creates one open Vikunja task, refreshes the Hermes todos cache/tile, and publishes a page with a `todos.complete` action.
- Note command creates one deduped note in the best category, refreshes the notes tile, and publishes a reference page.
- Summary command reads Vikunja-backed todos without mutating them, publishes a useful page, and logs the read steps.
- Calendar write command creates a pending approval instead of writing directly, refreshes the approvals tile, and explains the pending action in the page.

## Page Review Checklist

- No `<script>` tags.
- No `on*=` event handlers.
- No external `src`, `href`, `url()`, `@import`, font, or image loads.
- Page has a clear title, summary, and next action.
- Every action button has `data-action`.
- `data-payload` is valid JSON or omitted.
- The page remains useful if rendered inside an iframe with no JavaScript.

## State Review Checklist

Use SQL or MCP tools to confirm:

- `jobs.status` is `done` only when `jobs.page_id` is set.
- `job_events` contains short step logs for the command.
- `pages.html` contains the published page and is immutable after creation.
- `tiles.front` matches current database counts.
- Calendar write attempts create `approvals` rows with `status = 'pending'`.
- Notes do not duplicate existing content beyond the configured cap.

## Rollback

Rollback is safe when:

- The database schema has not been migrated in a backwards-incompatible way.
- The previous Hermes command and skill directory are still available.
- The app server still accepts the existing page and action contracts.

Rollback steps:

1. Repoint `AGENT_CMD` to the previous Hermes command.
2. Restore the previous skill directory and MCP package.
3. Restart the app service.
4. Run the first golden command to confirm job, page, event, and tile behavior.
