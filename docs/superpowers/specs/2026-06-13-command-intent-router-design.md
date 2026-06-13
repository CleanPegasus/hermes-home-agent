# Hermes Command Intent Router Design

Date: 2026-06-13

## Goal

The bottom command bar should accept one natural-language command and let Hermes decide whether it is a todo, a note, or an immediate agent job. Clear commands should be executed through existing Hermes Home tools. Ambiguous commands must ask the user for clarification before making any state-changing write.

This design keeps the web command bar simple. It sends text to `/api/command`; the Hermes agent performs routing after the job starts.

## Scope

Included:

- Classify each command as `todo`, `note`, `agent_job`, `mixed`, or `needs_clarification`.
- Extract structured todo fields: title, notes, project, labels or tags, due date, start date, and priority.
- Extract structured note fields: title, body, Obsidian category, tags, and duplicate-search query.
- Run `agent_job` commands immediately in the current job.
- Ask a focused clarification question when the intent or required fields are uncertain.
- Publish a durable result page only for `agent_job` work.
- Complete todo, note, and non-agent mixed commands with a lightweight job summary instead of a generated page.

Excluded:

- Future or recurring job scheduling.
- A server-side classifier before Hermes starts.
- A chat transcript as the main interaction model.
- Automatic writes when Hermes is unsure.

## Existing System Fit

The current app already has the right job boundary:

- `web/src/main.ts` submits bottom-bar text to `/api/command`.
- `server/app/main.py` creates a `Job`, commits it, and starts a background agent thread.
- `server/app/jobs.py` invokes `AGENT_CMD` with `HERMES_HOME_COMMAND` and `HERMES_HOME_JOB_ID`.
- `mcp/hermes_home_mcp/server.py` exposes tools for todos, notes, pages, approvals, job events, and tile updates.
- Local skills already describe todo handling, note categorization, page delivery, and tile refresh rules.

The new behavior should live at the agent boundary, not in the browser. The browser remains a transport and progress surface.

## Intent Model

Hermes should treat routing as the first step of every command. The router produces an internal decision:

```json
{
  "intent": "todo",
  "confidence": 0.92,
  "reason": "The command asks for a future action to be tracked.",
  "todo": {
    "title": "buy oat milk",
    "notes": null,
    "project_hint": "errands",
    "labels": ["groceries"],
    "due_at": "2026-06-14T18:00:00+05:30",
    "scheduled_for": null,
    "priority": 0
  }
}
```

The decision is not exposed as a user-facing artifact by default. It is used to choose the execution path and can be included in job diagnostics or page provenance.

## Routing Rules

### Todo

Use `todo` when the user wants something tracked as an action item, reminder, purchase, pickup, chore, follow-up, or task.

Execution:

1. Log that Hermes is classifying a todo.
2. Call `todos_projects_list` and `todos_labels_list`.
3. Infer title, notes, project, labels, due date, start date, and priority.
4. Convert natural-language dates into RFC3339 using the user's timezone.
5. Call `todos_create`.
6. Refresh the todos tile through existing tool behavior.
7. Mark the job done with a concise summary of the created todo. Do not publish a generated page.

Clarify before writing if:

- The command might be a note instead of a task.
- The task title is too vague to be useful.
- The user explicitly references a date or time but Hermes cannot infer it confidently.
- The project choice changes where the task will live and confidence is low.

### Note

Use `note` when the user wants to remember, store, file, capture, summarize, or preserve information.

Execution:

1. Log that Hermes is classifying a note.
2. Call `categories_list`.
3. Build a concise title, markdown body, category, tags, and duplicate-search query.
4. Call `notes_search` before writing.
5. Call `notes_append` if a matching note already captures the fact.
6. Call `notes_create` if no suitable note exists.
7. Refresh the notes tile through existing tool behavior.
8. Mark the job done with a concise summary of the saved or updated note. Do not publish a generated page.

Clarify before writing if:

- The command might be a todo instead of a note.
- The content is too vague to create a useful note.
- Hermes would need to store a secret, token, or credential.
- The intended category is unclear and choosing `inbox` would hide an important distinction.

### Agent Job

Use `agent_job` when the user wants Hermes to do work immediately: research, summarize, inspect, generate a report, compare options, diagnose something, or otherwise perform a multi-step task.

Execution:

1. Log that Hermes is running an immediate agent job.
2. Perform the requested work in the current job.
3. Use MCP tools for any durable state writes that the job requires.
4. Request approval for gated external writes.
5. Publish a result page with the result, source notes, skipped items, and next actions.

There is no scheduler in this design. If the user asks to run something later or repeatedly, Hermes should ask for clarification or explain that scheduling is not available in this slice.

### Mixed

Use `mixed` when a single command clearly contains more than one independent intent, such as "add buy milk to todos and remember that the guest wifi password is on the router label."

Execution:

1. Split the command into independent intents.
2. Apply the relevant todo, note, and agent job rules to each part.
3. If every part is clear, execute all clear parts in one job.
4. Publish a result page only if the mixed command includes an `agent_job` part. If the command only creates or updates todos and notes, finish with a lightweight job summary and no page.

Clarify before writing if any part is ambiguous or if executing only the clear parts would surprise the user.

### Needs Clarification

Use `needs_clarification` when the command cannot be safely routed or required fields are missing.

Rules:

- Do not create todos, notes, approvals, pages-as-results, or other durable user data except the clarification artifact itself.
- Ask one focused question.
- Prefer two to four concrete choices when possible.
- Preserve the original command and Hermes's draft interpretation.
- Let the user answer from the app and resume the original job context. Do not publish a generated page for the clarification prompt.

Examples:

- "milk tomorrow" -> "Should I add this as a todo, or save a note?"
- "remember to call Sam" -> "Should this be a todo with a deadline, or a note?"
- "send the thing to Priya" -> "What should I send?"

## Completion UX

Todo, note, and non-agent mixed commands should not open generated pages. They should end with job status `done`, a short `emoji` and `summary`, and relevant job events. The web app should treat `done` without `page_id` as a successful completion rather than an error.

The preferred UI after a successful non-page job is:

- Show a compact completion state with the job summary.
- Offer one-click navigation to the relevant surface, such as todos, notes, or history.
- Leave the command available in history for audit and retry.

Agent jobs remain page-oriented. A successful `agent_job` should publish a generated page because the result is usually a report, analysis, or artifact that needs space.

## Clarification UX

The current app can represent approval waits, but clarification should be first-class rather than pretending to be a failed job.

Add a clarification flow:

- New job status: `needs_clarification`.
- New table or JSON-backed record for clarification requests.
- New MCP tool: `clarifications_request(question, choices, draft, source_job_id)`.
- New API routes:
  - `GET /api/clarifications/{id}`
  - `POST /api/clarifications/{id}/answer`
- Web job detail shows the question, choices, optional free-text answer, and the original command.

When the user answers, the server should create a follow-up job that includes:

- Original command.
- Clarification question.
- User answer.
- Draft fields from the first routing attempt.

The follow-up job then runs Hermes again. It publishes a final page only if the clarified intent is `agent_job`; todo and note outcomes finish with a lightweight job summary.

## Agent Prompt Contract

The `AGENT_CMD` entrypoint should instruct Hermes to:

1. Read `HERMES_HOME_COMMAND`.
2. Route before writing.
3. Use the local Hermes Home skills:
   - `manage-todos` for todo commands.
   - `categorize-notes` for note commands.
   - `deliver-as-page` only for `agent_job` commands.
   - `keep-tiles-fresh` after state changes.
4. Ask clarification before writes if classification confidence is low.
5. Emit short job events at major steps.
6. Publish exactly one page for completed `agent_job` commands.
7. Finish todo, note, and non-agent mixed commands with `job_set_summary` and no `pages_publish`.

The prompt should define `agent_job` as immediate work only.

## Data Flow

Clear todo:

```text
bottom bar -> POST /api/command -> Job
  -> AGENT_CMD
  -> router: todo
  -> todos_projects_list, todos_labels_list
  -> todos_create
  -> job_set_summary
  -> web shows compact completion and links to todos
```

Clear note:

```text
bottom bar -> POST /api/command -> Job
  -> AGENT_CMD
  -> router: note
  -> categories_list, notes_search
  -> notes_create or notes_append
  -> job_set_summary
  -> web shows compact completion and links to notes
```

Immediate agent job:

```text
bottom bar -> POST /api/command -> Job
  -> AGENT_CMD
  -> router: agent_job
  -> perform work
  -> optional MCP writes or approvals
  -> pages_publish
  -> web opens /page/:id
```

Ambiguous command:

```text
bottom bar -> POST /api/command -> Job
  -> AGENT_CMD
  -> router: needs_clarification
  -> clarifications_request
  -> job status needs_clarification
  -> web shows question
  -> user answers
  -> follow-up Job runs with answer included
  -> page only if resolved intent is agent_job
```

## Error Handling

- If Vikunja is not configured, todo execution should fail cleanly with a job error explaining the missing configuration.
- If Obsidian is not configured, note execution should fail cleanly with a job error explaining `OBSIDIAN_VAULT_PATH`.
- If Hermes cannot classify the command, it should request clarification rather than fail.
- If an agent job requires unavailable tools or inaccessible data, it should publish a page that names what was skipped or inaccessible.
- If the clarification answer is empty, the API should reject it with a validation error and keep the job in `needs_clarification`.

## Testing

Backend tests:

- `/api/command` still creates jobs unchanged.
- `clarifications_request` creates a clarification and marks the job `needs_clarification`.
- Answering a clarification creates a follow-up job with original command and answer context.
- Job serialization includes `needs_clarification`.
- Existing `needs_approval`, `done`, `failed`, and `cancelled` behavior still works.
- `done` jobs without `page_id` serialize as successful completions.

MCP tests:

- `clarifications_request` records question, choices, draft fields, and source job id.
- The tool does not create todos or notes.
- Clarification records serialize consistently for SQLite and Postgres.

Frontend tests:

- The working screen treats `needs_clarification` as terminal for polling.
- Job detail renders clarification question and choices.
- Submitting an answer creates or opens the follow-up job.
- The bottom command bar still submits plain commands without routing logic in the browser.
- A `done` job without `page_id` shows a successful compact completion, not the "didn't finish" error screen.

Agent contract tests:

- Todo examples infer labels, dates, start dates, and priority.
- Note examples search before writing and choose categories.
- Ambiguous examples request clarification without writes.
- Agent-job examples run immediately and publish a result page.
- Todo and note examples finish without calling `pages_publish`.

## Acceptance Criteria

- A clear todo command creates a Vikunja todo with inferred metadata and finishes without a generated page.
- A clear note command writes or appends an Obsidian note with inferred category and tags and finishes without a generated page.
- A clear agent-job command runs immediately and opens a result page.
- An ambiguous command asks one clarification question and performs no todo or note write before the answer.
- Answering a clarification resumes the command through a follow-up job.
- The browser command bar does not contain todo/note/job business rules.
- The design does not add future or recurring scheduling.
