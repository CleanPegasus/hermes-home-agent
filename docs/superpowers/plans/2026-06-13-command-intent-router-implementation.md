# Command Intent Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the command intent router support from the approved design: clarification before ambiguous writes, successful non-page todo/note completions, and generated pages only for immediate agent jobs.

**Architecture:** Keep the browser command bar as a transport. Add first-class clarification persistence and API support on the FastAPI side, expose a matching MCP tool for the Hermes agent, and update the web client to treat `done` without `page_id` as success. The actual natural-language routing remains in the Hermes agent prompt/contract, not in the web browser.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/Postgres schema files, the Hermes MCP Python module, Vite TypeScript, Vitest, Pytest.

---

### Task 1: Add Clarification Persistence

**Files:**
- Modify: `server/app/models.py`
- Modify: `server/app/db.py`
- Modify: `db/schema.sql`
- Modify: `mcp/hermes_home_mcp/server.py`
- Test: `server/tests/test_api.py`

- [ ] **Step 1: Write failing backend schema/model tests**

Add tests that create the app, inspect the database, and assert a `clarifications` table exists with `question`, `choices`, `draft`, `status`, and job linkage columns. Add a second test that imports the MCP module against a SQLite database and verifies its schema includes the same table.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv --cache-dir /tmp/uv-cache --directory server run pytest tests/test_api.py -q
```

Expected: failures showing `clarifications` is missing.

- [ ] **Step 3: Implement model and schemas**

Add `Clarification` to `server/app/models.py` with `id`, `job_id`, `question`, `choices`, `draft`, `answer`, `status`, `follow_up_job_id`, `created_at`, and `answered_at`.

Update `server/app/db.py` lightweight migrations for existing databases and `db/schema.sql` for the deployment contract.

Update `mcp/hermes_home_mcp/server.py` SQLite schema and `JSON_COLUMNS` for `choices` and `draft`.

- [ ] **Step 4: Run tests to verify they pass**

Run the same Pytest command and confirm the schema assertions pass.

### Task 2: Add Clarification API Flow

**Files:**
- Modify: `server/app/main.py`
- Modify: `server/app/models.py`
- Modify: `server/app/jobs.py` if status helpers need adjustment
- Test: `server/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests for:

- `GET /api/jobs/{job_id}/timeline` includes pending clarification records.
- `GET /api/clarifications/{id}` returns the clarification and source job.
- `POST /api/clarifications/{id}/answer` rejects an empty answer.
- `POST /api/clarifications/{id}/answer` stores the answer, creates a follow-up job, copies the profile id, and returns `job_id`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv --cache-dir /tmp/uv-cache --directory server run pytest tests/test_api.py -q
```

Expected: route/status failures for missing clarification support.

- [ ] **Step 3: Implement API**

Add Pydantic input models for clarification answers. Add serializers for `Clarification`. Extend job timeline and diagnostics responses with `clarifications`.

Add:

- `GET /api/clarifications/{clarification_id}`
- `POST /api/clarifications/{clarification_id}/answer`

When answering, build a follow-up command that preserves the original command, question, answer, and draft fields. Create and start a follow-up job immediately. Mark the clarification answered and store the follow-up job id.

- [ ] **Step 4: Run tests to verify they pass**

Run the same Pytest command and confirm the API tests pass.

### Task 3: Add MCP Clarification Tool And Non-Page Job Summary Contract

**Files:**
- Modify: `mcp/hermes_home_mcp/server.py`
- Modify: `mcp/hermes_home_mcp/__init__.py`
- Test: `server/tests/test_api.py` or a new focused MCP test file if clearer

- [ ] **Step 1: Write failing MCP tests**

Add tests that call `clarifications_request(question, choices, draft)` with `HERMES_HOME_JOB_ID` set and assert:

- A clarification row is created.
- The source job status becomes `needs_clarification`.
- No page row is created.
- The tool is exported in `TOOLS` and package `__init__`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv --cache-dir /tmp/uv-cache --directory server run pytest tests/test_api.py -q
```

Expected: missing function/export failures.

- [ ] **Step 3: Implement MCP tool**

Add `clarifications_request(question, choices=None, draft=None, source_job_id=None)`. Validate non-empty question, normalize choices to a list of short strings, store draft JSON, set the source job status to `needs_clarification`, log a job event, and return `{"clarification": row, "needs_clarification": True}`.

Update `job_set_summary` so agent jobs can finish todo/note jobs without publishing pages: when called for the active job, set `status='done'` and `finished_at=CURRENT_TIMESTAMP` if the job is not terminal.

- [ ] **Step 4: Run tests to verify they pass**

Run the same Pytest command and confirm MCP tests pass.

### Task 4: Update Web Client For Clarifications And Done Without Page

**Files:**
- Modify: `web/src/api.ts`
- Modify: `web/src/jobs.ts`
- Modify: `web/src/main.ts`
- Modify: `web/src/ui.ts`
- Test: `web/src/jobs.test.ts`
- Test: `web/src/api.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Add tests for:

- `waitForJob` treats `needs_clarification` as terminal.
- `renderJobDetail` renders clarification questions and answer choices.
- `createApiClient().answerClarification()` posts the answer body.
- `statusEmoji("needs_clarification")` returns a distinct marker.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd web && npm test -- --run src/jobs.test.ts src/api.test.ts src/ui.test.ts
```

Expected: type/test failures for missing clarification status and API method.

- [ ] **Step 3: Implement frontend types and rendering**

Add `needs_clarification` to `Job["status"]`. Add a `Clarification` type and include `clarifications` in job detail responses.

Add `answerClarification(id, answer)` to the API client.

Update `waitForJob` terminal statuses to include `needs_clarification`.

Update `runCommand` so:

- `done` with `page_id` opens the page.
- `done` without `page_id` opens the job detail or a compact completion screen, not the error screen.
- `needs_clarification` opens the job detail.

Update `renderJobDetail` to show clarification questions, choices, answer input, and submit action.

- [ ] **Step 4: Run tests to verify they pass**

Run the same frontend test command and confirm it passes.

### Task 5: Contract Tests And Final Verification

**Files:**
- Modify: `server/tests/test_deployment_files.py` if deployment schema contract needs clarification coverage
- Modify: `docs/superpowers/specs/2026-06-13-command-intent-router-design.md` only if implementation reveals a required spec correction

- [ ] **Step 1: Add/adjust contract tests**

Ensure deployment schema and MCP exports include `clarifications_request` and `clarifications`.

- [ ] **Step 2: Run backend verification**

Run:

```bash
uv --cache-dir /tmp/uv-cache --directory server run pytest -q
```

Expected: all server tests pass.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
cd web && npm test -- --run && npm run build
```

Expected: all frontend tests pass and build succeeds.

- [ ] **Step 4: Commit implementation**

Stage only intended files and commit:

```bash
git add server/app mcp/hermes_home_mcp db/schema.sql web/src docs/superpowers/plans/2026-06-13-command-intent-router-implementation.md
git commit -m "Implement command clarification flow"
```

---

## Self-Review

Spec coverage:

- Todo/note jobs finish without generated pages: Task 3 and Task 4.
- Agent jobs still publish pages: Task 4 preserves page navigation for `done` with `page_id`.
- Ambiguous commands ask clarification before writes: Task 1 through Task 3.
- Clarification answer resumes via follow-up job: Task 2.
- Browser does not own routing: Tasks only add status/API/rendering, no browser classifier.
- No scheduling: no scheduler tables or recurrence logic are included.

Placeholder scan:

- No `TBD`, `TODO`, or intentionally vague implementation steps remain.

Type consistency:

- Status name is consistently `needs_clarification`.
- Tool name is consistently `clarifications_request`.
- API method is consistently `answerClarification`.
