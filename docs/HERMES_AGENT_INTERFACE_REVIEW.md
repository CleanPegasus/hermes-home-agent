# Hermes Agent Interface Review

## Purpose

This document explains how the current Hermes Home web app works, where it is already aligned with a good personal-agent interface, and what should change to make it a stronger day-to-day control surface for the Hermes agent.

The current product direction is sound: the app avoids a chat transcript as the main surface and instead treats Hermes work as commands, live jobs, durable generated pages, typed actions, and stateful home tiles. The main work now is to make that loop reliable, more transparent, and more complete.

## Executive Summary

Hermes Home is currently a local-first command center:

- The web client is a plain Vite and TypeScript app with no frontend framework.
- The start screen is a Metro-style tile grid driven by `/api/tiles`.
- A command submitted through the bottom command bar creates a server-side job through `/api/command`.
- The server runs either an external Hermes command from `AGENT_CMD` or a deterministic fallback agent.
- Job progress is stored in `job_events` and exposed as SSE-formatted text.
- A completed job is expected to publish one sanitized HTML page.
- The page is shown in a sandboxed iframe, while supported `data-action` buttons are extracted and rendered as native app buttons below the iframe.
- App state lives in SQLite for local development and SQLAlchemy models, with Postgres plus pgvector as the deployment contract.
- The MCP package exposes the agent-facing operations Hermes needs to create todos, notes, pages, approvals, tiles, calendar requests, and job events.

Implementation update: the client now supports `VITE_API_BASE`, a stored runtime API base, typed API errors, and a first-run setup screen for entering the local API token. The backend also exposes session and capability endpoints so the UI can distinguish auth, server, database, MCP, and agent state.

The biggest remaining product gap is that some backend and MCP concepts still need production-grade external integrations and deeper workflows. Approvals, job details, note categories, todo actions, retries, cancellation, settings, page pinning, note management, local calendar execution, action audit, diagnostics, source-aware follow-ups, and calendar/spend/channels/vitals surfaces now have first-pass implementations. Local JSON-file adapters exist for calendar, channel, and spend imports, with durable sync history and error reporting. Action audit entries can be filtered by action, status, source job, and source page, and individual audit records can be copied or downloaded. Page provenance records reads, writes, skipped items, and inaccessible items for fallback and MCP-published pages. A Codex tile can launch `codex exec` in the web app directory in yolo mode. The remaining work is real provider credentials and sync, route polish, richer provider-specific remediation, and deeper audit/provenance visualization.

## Current App Architecture

```text
user
  |
  v
web shell, Vite TypeScript
  |
  v
FastAPI server, bearer auth, routes under /api
  |
  +--> jobs, events, pages, tiles, todos, notes, approvals in database
  |
  +--> AGENT_CMD external Hermes process
  |
  +--> fallback local agent when AGENT_CMD is empty
  |
  v
MCP tools used by Hermes to write pages, state, and job events
```

Important files:

- `web/src/main.ts`: app boot, shell layout, navigation, command submission, screen switching.
- `web/src/api.ts`: typed browser API client and bearer-token header logic.
- `web/src/tiles.ts`: tile rendering.
- `web/src/jobs.ts`: working screen, SSE-text parsing, job polling, job list.
- `web/src/pages.ts`: generated page iframe rendering and action extraction.
- `web/src/todos.ts`: todo list rendering.
- `web/src/notes.ts`: note list rendering.
- `web/src/styles.css`: Metro-style visual system.
- `server/app/main.py`: FastAPI app, auth, API routes, serializers, background job task.
- `server/app/jobs.py`: job lifecycle, fallback agent, external agent invocation, action handling, tile refreshes.
- `server/app/sanitize.py`: server-side generated-page sanitizer.
- `server/app/db.py`: engine setup and seed categories and tiles.
- `server/app/models.py`: SQLAlchemy tables.
- `mcp/hermes_home_mcp/server.py`: agent-facing MCP tool functions.
- `db/schema.sql`: Postgres deployment schema and seed data.
- `skills/*/SKILL.md`: local Hermes behavior guidance.

## Web Client Walkthrough

### Boot And API Client

`web/src/main.ts` creates a singleton API client with `createApiClient()` and renders into `#app`.

`web/src/api.ts` reads `HOME_API_TOKEN` from `localStorage` and sends it as:

```text
Authorization: Bearer <token>
```

If no token exists, the client sends no bearer header. Since every `/api/*` route requires auth, the first load will fail unless the token has already been placed in local storage or the app is served behind something that injects auth.

Current behavior:

- `createApiClient()` reads the stored runtime API base first, then `VITE_API_BASE`, then same-origin paths.
- The setup screen lets the user save API base and token values into local storage.
- API failures now include HTTP status through a typed `ApiError`.

Remaining work:

- Add clearer diagnostics for server-down versus network-blocked versus bad-token states.
- Consider a same-origin deployment or Vite proxy for users who do not want to store an API base in the browser.

### Shell And Navigation

The shell is built by `shell(title, body)` in `main.ts`.

It renders:

- A top panorama row with the current title.
- A fixed agent state label, currently `hermes-01-listening`.
- A bottom nav with back and home controls.

Navigation still renders by replacing DOM through `setScreen()`, but the app now has a small route layer with browser history integration.

Current routed screens:

- `/`
- `/tile/:key`
- `/job/:id`
- `/page/:id`
- `/approval/:id`
- `/note/:id`
- `/action/:id`
- `/diagnostics/:job_id`
- `/codex/:run_id`
- `/settings`

Recommended follow-up:

- Add richer route-specific not-found copy.
- Update the top agent state from real job and connectivity status instead of static text.

### Start Screen

`showStart()` fetches `/api/tiles`, renders the tile grid, then adds suggestion chips and a fixed command form.

The seed tiles are:

- `jobs`
- `todos`
- `calendar`
- `notes`
- `approvals`
- `spend`
- `channels`
- `vitals`
- `codex`

All visible seed tiles now open a concrete screen. Calendar, channels, and spend can show local read-model data imported from configured JSON files; vitals shows system and audit counts; codex opens a local yolo-mode Codex runner rooted at `web/`.

Strengths:

- The tile grid is a good fast-glance home for an agent.
- Tile payloads are server-defined JSON, which keeps the client from owning business rules.
- The command bar is always near the thumb on mobile.

Gaps:

- Tiles do not live-refresh in the background.
- Tiles do not expose stale, working, error, or last-updated states clearly.
- Suggestion chips are hardcoded in the client instead of generated from agent capabilities or recent activity.
- Provider-backed tiles are still first-pass local views rather than full integrations.

### Command Submission

On form submit:

1. The input is trimmed.
2. The form is disabled.
3. `runCommand(text)` replaces the UI with a working screen.
4. `api.sendCommand(text)` posts to `/api/command`.
5. The client waits for job completion.
6. If the job finishes with `page_id`, the app loads and displays the page.
7. If the job fails, it shows a failure screen.

This flow matches the right mental model for Hermes: the user gives intent once, Hermes performs work, then returns an artifact.

Recommended improvements:

- Keep the command bar available on all primary screens, not only the start screen.
- Add command drafts and recent commands.
- Show which tools Hermes is allowed to use before submission when the command touches calendar, email, files, or external writes.
- Add cancel and "run in background" options for long jobs.

### Working Screen And Job Progress

`web/src/jobs.ts` renders a working screen with:

- The submitted command.
- Moving dots.
- A status line.
- An ordered step log.

`waitForJob()` now starts a bearer-authenticated fetch stream from `/api/jobs/{id}/stream` when the browser supports `ReadableStream`, while polling `/api/jobs/{id}` for terminal job status. It falls back to `/api/jobs/{id}/events` snapshots when streaming is unavailable.

Remaining limitation:

- The stream carries job events, but the job status is still polled.
- Event payloads are still simple text records; tool call metadata is not yet structured.
- Cancel requests now mark the job cancelled and external `AGENT_CMD` jobs poll for cancellation so the child process can be terminated.

Current implementation:

- Job detail renders timeline entries with timestamps and event kind.
- Diagnostic bundles are copyable from job detail.
- External `AGENT_CMD` stdout, stderr, and exit code are stored as bounded job diagnostics.

Recommended fix:

- Render structured tool calls with tool name, arguments summary, status, and result summary.
- Add richer elapsed-time and approval-wait states.

### Generated Pages

`web/src/pages.ts` renders the page returned from `/api/pages/{page_id}` in an iframe:

- `iframe.srcdoc = page.html`
- The iframe is sandboxed without `allow-same-origin`.
- `frame.title = page.title`

The client separately parses `button[data-action]` from the page HTML and creates native app buttons below the iframe. Clicking a native button calls `/api/actions`.

This is a good design because it keeps generated content mostly inert and lets the app own state-changing actions.

Gaps and risks:

- Action buttons inside the iframe appear visually but do not execute in-frame. That is okay technically, but the UI should make the native action strip feel like the actual action area.
- The action renderer now has pending, success, failure, and disabled states, but not undo.
- The server exposes action metadata, but the client does not yet fully use it for confirmation, danger styling, or payload validation.
- Page provenance now links back to the source job and records reads, writes, skipped items, and inaccessible items when pages are created by the fallback agent or MCP publisher. Follow-up forms can carry page/job/note context into the next command. Remaining work is better visualization of provenance and provider-specific source details.

### Todos View

`web/src/todos.ts` renders all todos returned by `/api/todos`.

Current behavior:

- Shows open, done, and dropped pivots.
- Lists todos with status, title, and source.
- Done items are visually struck through.
- Direct complete, reopen, and drop actions are available.

Recommended improvements:

- Make tabs real: today, upcoming, inbox, done, dropped.
- Add direct complete, reopen, drop, edit, due date, and source-page actions.
- Group by due date and scheduled date.
- Show whether a todo came from the user, Hermes, channel import, or page action.

### Notes View

`web/src/notes.ts` renders notes and includes a search input and category pivots.

Current behavior:

- Search filters the rendered note list.
- Category pivots filter the rendered note list.
- Category labels are fetched from the server.
- The starter taxonomy is aligned as `inbox`, `home`, `errands`, `health`, and `reference`.

Current implementation:

- Note detail, edit, archive, merge, source job links, and source-aware follow-up commands are implemented.

Recommended improvements:

- Add category move polish, richer source-page links, and memory correction workflows.

### Jobs View

The jobs tile opens `renderJobsList()`.

Current behavior:

- Shows command and status.
- Opens a job detail view with timeline events, page link, approval records, retry, cancel, diagnostics, and source-aware follow-up controls.

Recommended improvements:

- Add affected tiles and related state changes to the timeline.
- Add runtime duration and structured external tool summaries.
- Add filters for warnings, approvals, page publication, and state changes.

### PWA And Offline Behavior

The web app has a manifest and a service worker.

Current service worker behavior:

- Caches `/` and `/manifest.webmanifest`.
- Does not cache API responses.
- Avoids intercepting `/api/` requests.
- Falls back to `/` for non-API GET requests.

Recommended improvements:

- Add an explicit offline shell state.
- Queue draft commands locally but do not submit them until the API is reachable.
- Surface API connectivity and auth state in the agent state label.

## Server Walkthrough

### App Creation And Auth

`server/app/main.py` creates the FastAPI app, initializes the database, adds CORS, and declares all routes.

Every `/api/*` route depends on `require_auth()`. The token defaults to `dev-token` if `HOME_API_TOKEN` is not set.

Recommended improvements:

- Do not allow a production default token.
- Continue expanding `/api/session` diagnostics so the client can distinguish provider-down, database-down, bad-token, and agent-unavailable states.
- Add deployment guidance for replacing the local default token.

### Data Model

The SQLAlchemy models cover:

- Categories
- Notes
- Todos
- Jobs
- Job events
- Pages
- Tiles
- Approvals
- Calendar sync

This is the right object model for a personal agent. The core gap is not the schema; it is that several model-backed concepts are not yet exposed by the UI or route surface.

### Command Route And Job Lifecycle

`POST /api/command`:

1. Validates command text.
2. Creates a queued job.
3. Commits so the polling UI can see it.
4. Starts `run_agent_job()` as a background task.
5. Returns `job_id`.

`run_agent_job()` loads the job and calls `invoke_agent()`.

`invoke_agent()` chooses:

- `invoke_external_agent()` when `AGENT_CMD` is set.
- `invoke_fallback_agent()` when `AGENT_CMD` is empty.

External Hermes receives:

- `HERMES_HOME_JOB_ID`
- `HERMES_HOME_COMMAND`
- The parent environment, including `HOME_API_TOKEN` and `DATABASE_URL` if set.

The external job is considered successful only if it publishes a page. If the process exits without setting `job.page_id`, the job is marked failed.

This is a strong contract. It makes generated pages the durable output rather than a chat reply.

Recommended improvements:

- Add job timeout state distinct from generic failed.
- Add a "needs approval" completion path that still publishes a page explaining the pending approval.
- Continue enriching job diagnostics with structured tool metadata, affected rows, and provider health at the time of failure.

### Fallback Agent

The fallback agent:

1. Logs job events.
2. Converts commands into todo titles with simple prefix and suffix stripping.
3. Creates a todo.
4. Refreshes the todos tile.
5. Publishes a generated page with a `todos.complete` action.

It intentionally includes unsafe HTML in the fallback body to test the sanitizer. The stored page should not contain scripts or `onclick`.

This is useful for local verification, but it should stay clearly labeled as fallback behavior in the UI.

### Page Sanitization

There are two sanitizer paths:

- `server/app/sanitize.py` uses `nh3` with an allowed tag and attribute list.
- `mcp/hermes_home_mcp/server.py` has a regex-based `sanitize_page_html()`.

Current inconsistency:

- The deliver-as-page template includes a full document with `html`, `head`, `style`, `body`, and `main`.
- The `nh3` sanitizer does not allow several of those tags.
- The MCP regex sanitizer allows a broader shape and only strips some unsafe patterns.
- The written product rules say no external loads, but `nh3` allows `https` links and the MCP sanitizer allows `https://` URLs.

Recommended fix:

- Create one shared sanitizer contract used by the server route and MCP package.
- Decide whether pages are fragments or full documents, then enforce that consistently.
- If pages are allowed to include local CSS, allow `style` with strict CSS sanitization or move page styling into the iframe host.
- Block external network loads consistently.
- Add sanitizer tests for template output, links, style blocks, data-action payloads, and malicious attributes.

### Actions

`POST /api/actions` delegates to `handle_action()`.

Supported actions today:

- `todos.complete`
- `todos.reopen`
- `todos.drop`
- `approvals.request`
- `approvals.approve`
- `approvals.reject`

Unknown actions return `400`.

Recommended improvements:

- Return more updated entities and tile data after action completion.
- Action runs now support idempotency keys, durable audit rows, vitals visibility, drill-in, and links back to source pages/jobs when present. Remaining work is filtering and richer result summaries.
- Extend the registry with payload schemas, affected resources, and undo/reversal hints.

## MCP And Skill Contract

The MCP package gives Hermes direct tool functions for:

- Health checks.
- Category list and create.
- Todo query, create, update, and complete.
- Note list, create, append, move, and search.
- Calendar list events backed by local `calendar_events`.
- Calendar create/update through approval requests.
- Tile updates.
- Page publication.
- Approval requests.
- Job event logging.

The local skills define the desired agent behavior:

- `deliver-as-page`: publish one useful page instead of ending with chat.
- `keep-tiles-fresh`: refresh affected tiles after visible state changes.
- `categorize-notes`: categorize notes with dedupe and cap rules.

This is the right direction. The first naming and taxonomy drift pass has been corrected:

- `deliver-as-page` now names `pages_publish`.
- `categorize-notes` now names `categories_list`, `notes_search`, `notes_append`, and `notes_create`.
- The note category taxonomy is aligned between skill text, database seed data, MCP seed data, and UI category fetches.

Recommended fix:

- Add tool aliases only if Hermes already depends on older names.
- Use the generated capabilities endpoint more deeply in the UI so unavailable tools are hidden or clearly marked.

## What Works Well Already

The app has several strong product decisions:

- It is command-first, not chat-first.
- It stores durable pages as the result artifact.
- It separates generated content from state-changing app actions.
- It keeps state on the server and lets tiles be server-defined.
- It has a deterministic fallback path for local testing.
- It has a narrow external-agent seam through `AGENT_CMD`.
- It has tests for auth, command-to-page flow, sanitizer behavior, actions, tile rendering, and job polling.
- It already models approvals and now exposes a first-pass approval inbox.

These choices make it a good base for a Hermes interface.

## Main Interface Gaps

### 1. First-Run Setup Needs Better Diagnostics

The web app now has a first-run setup state for:

- API base URL.
- Bearer token.
- Server connectivity.
- Agent connectivity.
- Database health.
- MCP health.

The remaining work is to make diagnostics more specific and recovery-oriented: no token, bad token, server down, API base typo, database unavailable, and agent unavailable should each produce distinct next steps.

### 2. Live Work Needs More Structure

The current working screen now uses fetch streaming for job events and polls job status. Job detail also exposes timeline, retry, cancel, diagnostics, and bounded external process output. It should continue toward a full run monitor:

- Tool call names.
- Step status.
- Elapsed time.
- Warnings.
- Approval waits.
- Structured external tool output summaries.

### 3. Approvals Need Execution Semantics

Approvals are critical for trust. Calendar writes create approval requests, the approvals tile opens an inbox, and approved local calendar actions write into `calendar_events`.

The next iteration should make external-provider approvals executable, auditable, and reversible where possible:

- Pending requests.
- Requested action.
- Scope and risk.
- Expiration.
- Source command and job.
- Approve and reject buttons.
- Generated explanation page.

### 4. Generated Pages Need Better Action UX

Generated pages are the main artifact. They should support:

- Native sticky action bar.
- Success and error toasts.
- Action result summary.
- Undo when possible.
- Link back to source job.
- "Ask Hermes to revise this" command.
- "Pin to home" for useful pages.

### 5. Tiles Need State Semantics

Tiles should communicate more than count and label.

Recommended tile state fields:

```json
{
  "state": "fresh | working | stale | error | needs_approval",
  "count": 3,
  "line": "open",
  "sub": "filter due today",
  "updated_at": "2026-06-12T12:34:56Z"
}
```

This would let the UI show trust and freshness without hardcoded business rules.

### 6. Memory And Notes Are Too Passive

Hermes memory needs a browser, not just a list.

Add:

- Real search.
- Category filters from the server.
- Note detail pages.
- Source command and generated page links.
- Merge and archive.
- "Use this in next command".
- "Correct this memory".

### 7. Jobs Need Auditability

For an agent, the job ledger is trust infrastructure.

First-pass support now includes job list, timeline, page artifacts, approval records, retry, cancel, diagnostics, bounded stdout/stderr, and follow-up composition.

Add next:

- Full event timeline.
- Tool calls and outputs at a summarized level.
- Page artifact link.
- State changes caused by the job.
- Approval requests caused by the job.
- Error details.
- Retry and continue.

### 8. Calendar, Spend, Channels, And Vitals Need Real Providers

The home grid includes tiles that now open real local surfaces. Calendar supports approval-gated local writes, and calendar/channels/spend support JSON-file imports.

Options:

- Keep local adapters visible as development/test connectors.
- Add provider setup views explaining what credentials or files are missing.
- Keep tiles visible but clearly mark provider state as `not_configured`, `local_adapter`, or `provider_connected`.

The best agent interface should not imply that Hermes is monitoring something when there is no tool behind it.

## Recommended Product Shape

### Home: Agent Cockpit

Keep the Metro tile concept, but make the first screen a live cockpit:

- Top row: Hermes status, server status, last sync, settings.
- Tile grid: only configured capabilities plus clearly marked setup tiles.
- Command bar: always available.
- Recent activity strip: last 3 jobs with status.
- Approval alert: visible when anything is pending.

### Command Bar: Intent Composer

The command bar should support:

- Natural-language command entry.
- Recent commands.
- Suggested commands from server capabilities.
- Optional context attachments, such as selected note, page, todo, or calendar event.
- Clear submit modes: run now, draft, schedule, background.

### Run Monitor: Transparent Execution

The working screen should show:

- The command.
- Current phase.
- Event timeline.
- Tool calls in human terms.
- Elapsed time.
- Cancel.
- Hide and continue in background.
- Approval prompt when blocked.
- Final generated page.

### Page Viewer: Artifact Plus Actions

Generated pages should feel like Hermes' finished work:

- Full document area.
- Native action bar outside iframe.
- Page metadata: job, created time, sources, state changes.
- Revise, pin, share/export, and follow-up command controls.

### Work Surfaces

Each tile should open a real work surface:

- Todos: filtered task manager.
- Notes: memory browser.
- Jobs: audit ledger.
- Approvals: trust inbox.
- Calendar: read-only agenda plus approval-gated writes.
- Channels: inbound sources and import status.
- Spend: only if connected to a real source.
- Vitals: health/status of Hermes, MCP, jobs, database, and integrations.

## Implementation Roadmap

### Phase 0: Make Local Dev And First Run Reliable

Priority: highest.

Status: first-pass implementation exists. Remaining work is better diagnostic copy and deployment guidance.

Tasks:

- Improve setup diagnostics for bad token, server down, database unavailable, and agent unavailable.
- Document same-origin and separate-origin local run modes.
- Add a deployment guard for the local default token.
- Keep tests around `VITE_API_BASE`, stored API base, and token setup behavior.

Acceptance criteria:

- The README local run commands produce a working browser app.
- A new user can enter the token in the UI.
- The app distinguishes no token, bad token, server down, and agent unavailable.

### Phase 1: Real Job Streaming And Job Detail

Priority: high.

Status: first-pass implementation exists. Streaming, job detail, retry, cancel, diagnostics, and bounded external process output summaries are implemented. Remaining work is structured tool metadata and richer run-state visualization.

Tasks:

- Keep fetch streaming for job events and improve the monitor UI.
- Add structured tool metadata to job events.
- Add affected resources and tile refreshes to job diagnostics.
- Add explicit timeout status distinct from generic failure.

Acceptance criteria:

- A long-running Hermes job updates the UI without polling full event history.
- Failed jobs show actionable information.
- The user can leave and return to a running job.

### Phase 2: Action Registry And Approvals Inbox

Priority: high.

Status: first-pass implementation exists. Action metadata confirmations, idempotency keys, local calendar approval execution, action audit visibility, audit drill-in, source page/job links, audit filters, summaries, and copy/download controls are implemented. Remaining work is approval execution against external integrations and richer domain-specific result summaries.

Tasks:

- Extend action metadata with payload schemas and affected resources.
- Add undo/reversal hints where supported.
- Add provider-backed approval executors.
- Add richer domain-specific action result summaries.

Acceptance criteria:

- Calendar write requests become visible approval cards.
- Generated pages can point to approval review.
- Repeated action clicks are idempotent or safely disabled.

### Phase 3: Complete Core Work Surfaces

Priority: medium.

Status: first-pass implementation exists for todos, notes, jobs, approvals, page pinning, source-aware follow-ups, calendar, spend, channels, vitals, JSON-file connector sync, connector sync history, and connector error reporting. Remaining work is production provider connectors and deeper workflows.

Tasks:

- Make todo pivots functional.
- Add direct todo actions.
- Fetch categories from the server.
- Align category taxonomy across seed data, skills, and UI.
- Implement note search and filters.
- Polish note category moves and source-page links.
- Connect calendar, spend, and channels to external providers when credentials/tools are available.
- Add connector sync scheduling and provider-specific remediation guidance.

Acceptance criteria:

- Every visible home tile opens a meaningful screen.
- Notes and todos are useful without writing a command.
- UI state matches database state after actions.

### Phase 4: Agent Capability And Trust Layer

Priority: medium.

Tasks:

- Expand the current capabilities endpoint from configured MCP/tools.
- Show what Hermes can read and write at provider level.
- Show integration status, last sync, and sync errors for calendar, channels, spend, and other tools.
- Add a golden-command verification view using `docs/upgrade.md`.
- Store and display agent version and skill version.

Acceptance criteria:

- The user can tell what Hermes is configured to do.
- Upgrade regressions are visible from the app.
- The app does not present unconfigured tools as active.

### Phase 5: Polish, Accessibility, And Mobile Fit

Priority: medium.

Tasks:

- Add keyboard focus styles.
- Add screen-reader labels for dynamic job events.
- Respect reduced motion more selectively.
- Stabilize tile animation offsets.
- Add safe-area and compact-screen tests.
- Add command bar on all major screens.

Acceptance criteria:

- The interface remains usable on mobile and desktop.
- Text does not overlap in dense states.
- Motion does not hide important state changes.

### Phase 6: In-App Codex Runner

Priority: local power-user.

Status: first-pass implementation exists. A `codex` tile opens a prompt screen, creates durable Codex run records, launches `codex exec --dangerously-bypass-approvals-and-sandbox` with `-C web`, shows status plus stdout/stderr tails, warns through current dirty-worktree status, records before/after git status and diff stats, and can cancel queued/running Codex runs.

Remaining work:

- Add branch naming and commit/PR helpers.
- Add richer post-run summaries of changed files.
- Add safeguards for running multiple Codex tasks concurrently.

## Suggested API Additions

```text
GET    /api/session
GET    /api/capabilities
GET    /api/categories
GET    /api/approvals
GET    /api/approvals/{id}
POST   /api/approvals/{id}/approve
POST   /api/approvals/{id}/reject
GET    /api/jobs/{id}/timeline
GET    /api/jobs/{id}/diagnostics
POST   /api/jobs/{id}/cancel
POST   /api/jobs/{id}/retry
GET    /api/pages
POST   /api/pages/{id}/pin
POST   /api/pages/{id}/unpin
GET    /api/action-runs
GET    /api/action-runs/{id}
GET    /api/calendar
GET    /api/channels
GET    /api/spend
GET    /api/vitals
GET    /api/connectors
POST   /api/connectors/sync
GET    /api/codex
GET    /api/codex-runs
GET    /api/codex-runs/{id}
POST   /api/codex-runs
POST   /api/codex-runs/{id}/cancel
```

For action metadata:

```json
{
  "name": "todos.complete",
  "label": "mark done",
  "danger": "low",
  "requires_confirmation": false,
  "payload_schema": {
    "type": "object",
    "required": ["todo_id"]
  },
  "refresh": ["todos", "tiles"]
}
```

## Suggested UI Screens

### Setup

Shown when auth or API connection fails.

Fields:

- API base URL.
- Home API token.

Status checks:

- Server reachable.
- Auth valid.
- Database initialized.
- Agent command configured.
- MCP health.

### Home

The current tile grid, plus:

- Agent status.
- Connection status.
- Pending approvals alert.
- Recent jobs.
- Always-available command bar.

### Run

For a command/job:

- Command.
- Current status.
- Live timeline.
- Tool summaries.
- Cancel or background.
- Final page or approval prompt.

### Page

For a generated page:

- Page iframe.
- Native action bar.
- Source and job metadata.
- Follow-up command bar.

### Approvals

For approval-gated actions:

- Pending approval list.
- Scope details.
- Source command.
- Approve/reject.
- Expiration.

### Memory

For notes:

- Search.
- Categories.
- Note detail.
- Source links.
- Correct/archive/merge.

### Jobs

For audits:

- Job list.
- Timeline details.
- Artifacts.
- State changes.
- Retry/cancel.

### Codex

For changing the web app from inside Hermes Home:

- Prompt form rooted at `web/`.
- Yolo-mode run records.
- Status and output tails.
- Recent run list.

## Security And Trust Recommendations

- Keep generated page iframes sandboxed without `allow-same-origin`.
- Use one sanitizer implementation and one page contract.
- Treat generated pages as untrusted artifacts.
- Keep actions outside the iframe.
- Validate all action payloads server-side.
- Continue enriching action audit drill-ins, result summaries, and export/copy support.
- Use cookie auth or stream tokens if real SSE is added.
- Do not rely on `dev-token` outside local development.
- Make approval-gated writes impossible to bypass through page actions.
- Treat the Codex yolo tile as a local-only power tool; it intentionally bypasses Codex approvals and sandboxing.

## Test Recommendations

Keep the existing tests and add coverage for:

- `VITE_API_BASE` request routing.
- First-run token setup and bad-token display.
- Streaming event parsing and polling fallback.
- Job detail rendering.
- Connector JSON sync imports, sync history, and provider error display.
- Action audit filtering, drill-in, and source link rendering.
- Action audit copy/download controls.
- Codex yolo tile and run record behavior.
- Approval list and approve/reject flow.
- Action pending, success, failure, and duplicate-click behavior.
- Category taxonomy consistency.
- Sanitizer parity between server and MCP publication.
- Generated page iframe sandbox attributes.
- Provider tiles marked clearly as local adapter, not configured, or provider connected.

## Highest-Impact Next Changes

If only a few changes happen first, do these:

1. Add production provider connectors for calendar, channels, and spend.
2. Improve provenance visualization and provider-specific source details.
3. Add Codex branch naming plus commit/PR helpers.
4. Add connector sync scheduling plus provider-specific remediation guidance.
5. Add richer route-specific not-found copy.

Implementation update: the original top-five items now have first-pass implementations, including first-run setup, idempotent actions, page pinning, note detail/edit/archive/merge, external-process cancellation polling, bounded stdout/stderr diagnostics, local calendar approval execution, action audit drill-in/filter/copy/download controls, richer page provenance, source-job/source-page links, source-aware follow-ups, diagnostic bundles, JSON-file connector sync, connector sync history/error reporting, route/history/loading/not-found support, URL-persisted vitals filters, Codex yolo tile with cancellation and git summaries, and calendar/spend/channels/vitals surfaces.

These changes would move Hermes Home from a promising demo shell to a reliable interface for supervising an agent.
