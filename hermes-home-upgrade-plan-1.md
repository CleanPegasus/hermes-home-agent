# Hermes Home Upgrade Plan (Detailed)

## Context

Hermes Home is a personal agent dashboard: a vanilla-TypeScript Metro/Windows-Phone-style SPA (`web/`), a FastAPI server (`server/app/`), and an MCP server (`mcp/hermes_home_mcp/server.py`) that the Hermes agent uses to act on todos, notes, pages, and tiles. Jobs are created by `POST /api/command`, run either by an external agent subprocess (`AGENT_CMD` + `HERMES_HOME_*` env vars) or a built-in fallback agent, and always finish by publishing a sanitized HTML page.

This upgrade covers 11 user requirements: (1) emoji-rich prettier UI, (2) cohesive/stable UX, (3) polished codex page as the "modify this app" surface (settings stays minimal), (4) Obsidian-vault notes replacing DB notes, (5) deep Vikunja integration (projects/labels/priority), (6) agent profiles created from the UI, (7) no UI bugs, (8) gap-free beautiful tile grid, (9) pretty jobs/todos/notes pages, (10) a tile-style chat history page with emoji + short description per chat, (11) smart todo categorization (right project/labels/due/priority automatically).

**User decisions (settled, do not relitigate):**
- Obsidian = vault folder on the server (`OBSIDIAN_VAULT_PATH`); markdown + YAML frontmatter; migrate existing DB notes; user syncs the folder externally (Syncthing/iCloud/Obsidian Sync).
- Profiles = persona/system-prompt per profile; picker on start-page command bar; a profiles tile → page to choose/create/edit profiles; jobs record their profile.
- History tile emoji/summary = agent-generated via a new MCP tool, with a keyword-heuristic fallback for old jobs.
- Settings page stays minimal (API base + token); the existing codex page gets a chat-style polish instead.

## Critical architectural constraints (verified in exploration)

1. **The MCP server does not call the HTTP API.** It opens the database directly and duplicates Vikunja logic. Every schema change must be mirrored in **four places**:
   - `server/app/models.py` (SQLAlchemy models)
   - `db/schema.sql` (Postgres DDL + seeds)
   - `server/app/db.py` (`apply_lightweight_migrations` for existing DBs + `SEED_TILES`/`SEED_CATEGORIES`)
   - `mcp/hermes_home_mcp/server.py` (`SQLITE_SCHEMA` DDL + `ensure_sqlite_column` calls + its own seed lists)
2. **Tile `front`/`back` are free-form JSON columns** — emoji can be added without schema changes.
3. **Page HTML is sanitized** by `server/app/sanitize.py` (nh3) — no `<script>`, no event handlers; pages stay immutable artifacts.
4. **MCP tool names/signatures are the agent contract.** All changes must be additive (new tools, new optional params) or signature-preserving, so a running Hermes agent with pinned skills keeps working mid-upgrade.

**Reusable utilities to build on (do not reinvent):**
- `update_tile()`, `refresh_todos_tile()`, `refresh_notes_tile()`, `refresh_jobs_tile()`, `refresh_approvals_tile()`, `refresh_calendar_tile()` in `server/app/jobs.py`
- `ACTION_REGISTRY` + idempotent action-run pattern in `server/app/jobs.py` / `main.py`
- `serialize_job` / `serialize_todo` / `serialize_note` helpers in `server/app/main.py`
- `renderTile`, `renderTileFace`, `getTileShape`, `METRO_TILE_SHAPES_BY_KEY` in `web/src/tiles.ts`
- `shell()`, `visit()`, route dispatch in `web/src/main.ts` (routes at ~lines 46–109)
- `.tile-grid` CSS (`web/src/styles.css` ~lines 68–78): 4 cols mobile / 6 cols ≥760px, `grid-auto-rows: clamp(72px, 22vw, 112px)`, `--tile-col-span`/`--tile-row-span` vars per shape
- `VikunjaClient` + `vikunja_request` in `server/app/vikunja.py`; cache upsert in `server/app/todo_provider.py`
- Existing test patterns: `FakeVikunja` injection in `server/tests/test_api.py`; vitest with happy-dom; Playwright e2e with stubbed API routes in `web/e2e/app.spec.ts`

Each phase below leaves the app fully working and shippable.

---

## Phase 1 — Bug fixes + shared UI helpers (req 7; groundwork for everything)

### 1.1 Fix known bugs
- `web/src/codex.ts` (~line 15): eyebrow incorrectly reads `settings tile` — change to `codex`; change `h1` from "new chat" to something accurate ("codex").
- `web/src/main.ts` (~lines 81–92): the `/action/:id` and `/codex/:id` route blocks have indentation drift — normalize (and re-read for logic errors while there).
- Hard-coded suggestion chips in `main.ts` (~lines 150–162): keep, but move the string array to a named constant `COMMAND_SUGGESTIONS` at top of file so Phase 5 can vary it per profile.

### 1.2 New `web/src/ui.ts` — shared render helpers
Extract the helpers currently copy-pasted across `codex.ts`, `surfaces.ts`, `jobs.ts`, `approvals.ts`, `main.ts`:

```ts
export function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K]
export function addFact(list: HTMLElement, label: string, value: string): void
export function factsList(facts: Array<[string, string]>): HTMLElement      // <dl class="facts">
export function block(title: string, ...children: HTMLElement[]): HTMLElement
export function shortDate(iso: string | null): string                       // "jun 12, 14:03"
export function relativeDate(iso: string | null): string                    // "2h ago" — new, for history tiles
export function emptyState(emoji: string, line: string, hint?: string): HTMLElement
export function chip(text: string, color?: string): HTMLElement             // <span class="chip"> — used by todos labels, notes tags
export function statusEmoji(status: string): string                         // queued ⏳ running ⚙️ done ✅ failed ❌ cancelled 🛑 needs_approval 🛡️
```

Swap all pages over to these helpers (pure refactor, no behavior change). This is the cohesion backbone — every later phase uses `emptyState`, `chip`, `statusEmoji`, `relativeDate`.

### 1.3 Tests
- `web/src/ui.test.ts` (new): cover `shortDate`, `relativeDate`, `statusEmoji`, `chip` escaping.
- `web/src/codex.test.ts`: assert eyebrow text is `codex`.
- Run full baseline: `cd server && uv run pytest`, `cd web && npm test && npx playwright test`.

---

## Phase 2 — Tile grid alignment + emojis (req 1, 2, 8)

### 2.1 Gap-free deterministic packer (`web/src/tiles.ts`)
Problem: CSS `grid-auto-flow: dense` still leaves holes with mixed 1×1 / 2×1 / 1×2 / 2×2 shapes. Replace implicit placement with explicit coordinates computed in TS:

```ts
export interface PackedTile { tile: Tile; shape: TileShape; col: number; row: number; }

export function packTiles(tiles: Tile[], columns: number): PackedTile[]
```

Algorithm (skyline):
1. Maintain `heights: number[]` = next free row per column.
2. Iterate tiles in `sort` order. For each tile's (colSpan, rowSpan), find the leftmost-lowest position where `colSpan` consecutive columns are all free at the same row.
3. **Hole-avoidance lookahead:** before placing a 2-wide tile that would strand a 1-wide, 1-tall hole, scan the next 2 tiles for a 1×1/1×2 that fills the hole and place it first (bounded lookahead keeps original order mostly intact).
4. Return explicit positions; `renderTile` sets `style.gridColumn = "${col+1} / span ${colSpan}"` and `style.gridRow = "${row+1} / span ${rowSpan}"`. Keep the `--tile-col-span/--tile-row-span` vars for the shape CSS (sizing/typography), drop reliance on `dense` flow.
5. Pure function, no DOM — directly unit-testable.

Responsive: the column count differs (4 vs 6). Pack at render time using a `matchMedia("(min-width: 760px)")` check, and re-render the grid on the media query's `change` event (the start page already re-renders on data refresh; hook into the same path).

Make `METRO_TILE_SHAPES_BY_KEY` the single explicit source for every seeded key, and add entries now for the two upcoming tiles: `history: "wide"`, `profiles: "wide"`.

### 2.2 Emoji on tiles (no schema change)
- `web/src/api.ts`: `TileFace` gains `emoji?: string`.
- `web/src/tiles.ts` `renderTileFace`: render `<span class="tile-emoji">` before `tile-line` when present.
- `web/src/styles.css`: `.tile-emoji { font-size: 28px; line-height: 1; display: block; margin-bottom: 4px; }` (scaled up inside `tile-shape-large`).
- `server/app/jobs.py`: each `refresh_*_tile` adds `"emoji"` to the front dict — jobs ⚙️, todos ✅, approvals 🛡️, calendar 📅, notes 📝.
- Seeds: `db/schema.sql` tiles seed JSON + `server/app/db.py` `SEED_TILES` add spend 💸, channels 📨, vitals 💓, codex 🛠️ (and later history 🕘, profiles 🎭).
- `mcp/hermes_home_mcp/server.py`: its `refresh_todos_tile` / `refresh_notes_tile` mirror the emoji field.

### 2.3 List-row emojis
- `web/src/jobs.ts`: job rows prefix `statusEmoji(job.status)`.
- `web/src/todos.ts`: ✅ on done rows, 📅 next to due dates.
- `web/src/approvals.ts`: 🛡️ pending, ✅ approved, ❌ rejected, ⏰ expired.

### 2.4 Tests
- `web/src/tiles.test.ts`: packer produces zero holes for (a) the 9-tile seed set at 4 and 6 columns, (b) randomized shape sequences (property-style loop over ~50 random lists, assert every cell below the skyline is covered); emoji face renders; HTML-escaping still holds.
- `server/tests/test_api.py`: `GET /api/tiles` payload includes `emoji` for seeded tiles.
- Manual: verify both breakpoints and the flip animation still align (the 3D flip uses the tile's own box, so explicit placement is safe, but confirm).

Risk: `grid-auto-rows` clamp + 760px breakpoint interplay — verify visually; keep `.tile-grid` structure otherwise untouched.

---

## Phase 3 — Job emoji/summary + History page (req 10)

### 3.1 Schema (4-place mirror)
`jobs` gains three nullable columns (add `profile_id` now so the jobs table is migrated only once; it's used in Phase 5):

```sql
ALTER TABLE jobs ADD COLUMN emoji TEXT;        -- single emoji, agent- or heuristic-set
ALTER TABLE jobs ADD COLUMN summary TEXT;      -- <= 140 chars
ALTER TABLE jobs ADD COLUMN profile_id TEXT;   -- FK-by-convention to agent_profiles.id
```
- `server/app/models.py` `Job`: three new `Column(Text, nullable=True)`.
- `db/schema.sql`: columns in the `jobs` CREATE TABLE.
- `server/app/db.py` `apply_lightweight_migrations`: three ensure-column calls.
- `mcp/hermes_home_mcp/server.py`: `SQLITE_SCHEMA` jobs DDL + three `ensure_sqlite_column(connection, "jobs", ...)` calls.

### 3.2 Server
`server/app/jobs.py` — new pure function:

```python
HISTORY_EMOJI_RULES = [
    (("todo", "buy", "remind", "task"), "✅"),
    (("summarize", "summary", "research", "find", "look up"), "🔎"),
    (("note", "file", "remember", "write down"), "📝"),
    (("calendar", "schedule", "meeting", "event"), "📅"),
    (("spend", "budget", "money", "cost"), "💸"),
]

def derive_history_meta(command: str, status: str) -> tuple[str, str]:
    """Heuristic (emoji, summary) for jobs that never got an agent-set summary."""
    # failed/cancelled override -> ⚠️ / 🛑 ; else first keyword match; default 💬
    # summary = command stripped, collapsed whitespace, truncated to 60 chars with ellipsis
```

- `invoke_fallback_agent`: set `job.emoji`/`job.summary` explicitly when it completes (it knows what it did: created a todo → ✅ + "added '<title>' to todos").
- `server/app/main.py` `serialize_job`: return `emoji`/`summary`, computing `derive_history_meta(job.command, job.status)` when the columns are null — old jobs get coverage for free, **no backfill migration needed**.
- `GET /api/jobs`: add `limit: int = 50` query param (history page requests `limit=200`).

### 3.3 MCP tool (additive)
```python
async def job_set_summary(emoji: str, summary: str, job_id: str | None = None) -> dict:
    """Set the history-tile emoji and short summary for the current job.
    job_id defaults to HERMES_HOME_JOB_ID. summary trimmed to 140 chars.
    Validates emoji is 1 grapheme-ish (len <= 8 after strip); returns {ok, job_id}."""
```
Register in the MCP `TOOLS` list. Purely additive — running agents unaffected until skills mention it.

### 3.4 Skill update
`skills/deliver-as-page/SKILL.md` — append a section:

> **Finish every job with a summary.** Before or right after `pages_publish`, call `job_set_summary` with exactly one emoji that captures the task type and a ≤10-word plain description of what you did (e.g. ✅ "added oat milk to errands"). This powers the history page.

### 3.5 Frontend
- **New `web/src/history.ts`**:
  ```ts
  export function renderHistory(root: HTMLElement, jobs: Job[], onOpen: (job: Job) => void): void
  ```
  Renders a Metro tile grid (reuse `.tile-grid` + `packTiles`): each job = a tile with `.history-tile` variant — emoji large (reuse `.tile-emoji`), `summary` as `tile-line`, `relativeDate(created_at)` as `tile-meta`, accent color by status (done = tile color, failed = `#E51400`, running = pulsing). Shape assignment: cycle `[wide, small, small, tall, wide, small]` for visual rhythm (deterministic by index, so the packer keeps it gap-free). Group headers by day ("today", "yesterday", "earlier") as full-width separators between grids.
- `web/src/main.ts`: route `/history` → `showHistory()` (fetch `getJobs(200)`, render, tile tap → `visit('/job/' + id)`); `openTile("history")` → `visit("/history")`.
- `web/src/api.ts`: `Job` gains `emoji: string | null; summary: string | null;`; `getJobs(limit?: number)`.
- Seed `history` tile: key `history`, size `w`, sort 95, emoji 🕘, in `db/schema.sql` + `server/app/db.py` `SEED_TILES`; shape map entry already added in Phase 2.
- `web/src/styles.css`: `.history-tile`, day separators, status accent classes.

### 3.6 Tests
- `server/tests/test_api.py`: `derive_history_meta` cases (todo→✅, failed→⚠️, default 💬, truncation); `serialize_job` fallback when columns null; `job_set_summary` round-trip (call the async MCP function directly against the sqlite test DB with `HERMES_HOME_JOB_ID` monkeypatched — same style as existing MCP tests); `/api/jobs?limit=` respected.
- `web/src/history.test.ts` (new): renders one tile per job, emoji and summary text present, failed jobs get danger class, day grouping.
- `web/e2e/app.spec.ts`: history route renders tiles from stubbed `/api/jobs`.

---

## Phase 4 — Vikunja projects/labels/priority + smart todo skill (req 5, 11; todos part of 9)

### 4.1 `server/app/vikunja.py` — client extensions
```python
def list_projects(self) -> list[dict]            # GET /projects -> [{id, title, hex_color}]
def list_labels(self) -> list[dict]              # GET /labels   -> [{id, title, hex_color}]
def ensure_label(self, title: str) -> dict       # find by title (case-insensitive) else PUT /labels
def set_task_labels(self, task_id, label_ids)    # PUT /tasks/{id}/labels per label id
```
- `create_task(...)` gains `priority: int | None = None`, `label_titles: list[str] | None = None`, `project_id: int | None = None` (currently always default project). After create, ensure+attach labels.
- `normalize_task(task, project_titles: dict[int, str])`: read `task["priority"]`, `task["labels"]`, and resolve the real project title from the map (replaces the `f"project {project_id}"` placeholder).
- Defensive: Vikunja versions differ on duplicate-label errors (400 vs 409 vs silent) — `ensure_label` lists first, and label-attach failures degrade to a logged warning, never fail the task creation. Label attach is N+1 HTTP calls — acceptable at personal scale.

### 4.2 `server/app/todo_provider.py`
- `refresh_vikunja_cache`: fetch `list_projects()` once per refresh; pass the `{id: title}` map into `normalize_task`; store labels into the existing `tags` array column and `priority` into the new column.
- `create_todo` / `update_todo`: pass through `project_id`, `label_titles`, `priority`.

### 4.3 Schema (4-place mirror)
`todos` gains `priority INTEGER` (nullable). Labels reuse the existing `tags TEXT[] / JSON` column — no new column.

### 4.4 API (`server/app/main.py`)
- `GET /api/todos` response gains:
  ```json
  { "todos": [...], "projects": [{"id": 1, "title": "personal", "hex_color": ""}],
    "labels": [{"id": 3, "title": "groceries", "hex_color": "#4CAF50"}],
    "configured": true, "warning": null }
  ```
  Projects/labels fetched alongside the refresh, failure-tolerant (empty arrays + warning on Vikunja error).
- `serialize_todo`: add `priority`, keep `tags`, `project_id`, `project_title`.

### 4.5 MCP tools (additive, contract-safe)
```python
async def todos_projects_list() -> dict      # {"projects": [{id, title}]}
async def todos_labels_list() -> dict        # {"labels": [{id, title, hex_color}]}
# extended signatures (new params optional, defaults preserve existing callers):
async def todos_create(title, notes=None, due_at=None, scheduled_for=None,
                       project_id=None, labels=None, priority=None) -> dict
async def todos_update(todo_id, changes: dict) -> dict   # changes may now include project_id/labels/priority
```
Mirror `priority`/real-project-title handling in the MCP's own `normalize_vikunja_task` + cache upsert (remember: MCP duplicates Vikunja logic).

### 4.6 New skill `skills/manage-todos/SKILL.md`
Content outline:
- **When**: any command that creates or edits a todo.
- **Procedure**: 1) `todos_projects_list` + `todos_labels_list` first. 2) Pick the project whose title best matches the topic (groceries/errands → errands-like project; work topics → work project; else default). 3) Reuse existing labels case-insensitively; create at most 1 new label per todo, lowercase, singular. 4) Parse natural-language dates ("friday", "next week", "tomorrow 6pm") to RFC3339 in the user's timezone for `due_at`. 5) Priority mapping: "urgent/asap" → 5, "important" → 4, default → 0/none, "someday/maybe" → 1. 6) The published page must state which project, labels, due date, and priority were set so the user can verify at a glance.
- **Guardrails**: never move existing todos between projects unless asked; never delete labels.

### 4.7 Frontend — pretty todos page (`web/src/todos.ts` + `styles.css`)
- Row layout: title; project `chip()` (neutral); label chips colored with the label's `hex_color`; due date with 📅, red `.overdue` class when past; priority shown as `!`–`!!!` dots for 3–5.
- Filters: keep the status pivots (open/done/all); add a second pivot row of projects (from response `projects`, "all" first) and a tappable label-chip filter strip. Filter logic stays client-side, pure functions exported for tests.
- Setup state: when `configured: false`, render `emptyState("🔗", "connect vikunja", warning)`.

### 4.8 Tests
- `server/tests/test_api.py`: extend `FakeVikunja` with projects/labels endpoints; cases — create todo with project+labels+priority lands in cache correctly; `/api/todos` includes projects/labels; Vikunja-down degrades to warning; `ensure_label` reuses existing label.
- `web/src/todos.test.ts`: project pivot filtering, label filtering, overdue class, priority rendering.

---

## Phase 5 — Agent profiles (req 6)

### 5.1 Schema
New table (models.py + schema.sql + db.py seeds + MCP `SQLITE_SCHEMA`):

```sql
CREATE TABLE agent_profiles (
    id TEXT PRIMARY KEY,            -- uuid
    slug TEXT UNIQUE NOT NULL,      -- "research", "coding", ...
    name TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '🤖',
    color TEXT NOT NULL DEFAULT '#1BA1E2',
    persona TEXT NOT NULL DEFAULT '',     -- system-prompt text injected at invocation
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```
Seeds (`SEED_PROFILES` in `server/app/db.py`, insert-if-missing like `SEED_TILES`):
🪄 personal assistant (**default**), 🧠 research agent, 💻 coding agent, 💰 financial helper — each with a 2–4 sentence starter persona. `jobs.profile_id` already exists (Phase 3).

### 5.2 Server (`server/app/main.py`)
```
GET    /api/profiles               -> {profiles: [...], default_id}
POST   /api/profiles               -> create (ProfileIn: name, emoji, color, persona; slug auto from name)
PATCH  /api/profiles/{id}          -> partial update (incl. is_default=true -> clears previous default)
DELETE /api/profiles/{id}          -> 409 if is_default; jobs keep dangling profile_id (serializer tolerates)
```
- `CommandIn` gains `profile_id: str | None`; `/api/command` resolves the profile (explicit id → else default) and passes to `create_job`.
- `GET /api/jobs` gains `profile_id` filter; `serialize_job` embeds `profile: {id, name, emoji, color} | null` (load all profiles into a dict once per request — there will be <20).

### 5.3 Server (`server/app/jobs.py`)
- `create_job(session, command, profile_id=None)` stores `profile_id`.
- Extract a testable helper:
  ```python
  def agent_environment(job: Job, profile: AgentProfile | None) -> dict[str, str]:
      # existing HERMES_HOME_JOB_ID / HERMES_HOME_COMMAND / DATABASE_URL / HOME_API_TOKEN
      # plus, when profile: HERMES_HOME_PROFILE_ID / _NAME / _PERSONA
  ```
  `invoke_external_agent` uses it. Env-var injection (not command-wrapping) keeps `HERMES_HOME_COMMAND` clean; old agents ignore unknown vars; the Hermes harness prepends `HERMES_HOME_PROFILE_PERSONA` to its system prompt (document this in `docs/HERMES_SERVER_INSTALL.md` agent-contract section).
- Fallback agent: just records `profile_id` (no behavior change).

### 5.4 Frontend
- **New `web/src/profiles.ts`**:
  - `renderProfilesPage`: grid of profile tiles (emoji + name on profile color; reuse `.tile` styles) + a dashed "➕ new profile" tile. Tap profile → `/profile/:id` focus view; long-press/edit glyph → editor.
  - `renderProfileFocus`: profile header (emoji, name, persona preview), a command form that submits with this profile's id, and the profile's recent jobs (`getJobs({profile_id})`) as compact rows.
  - `renderProfileEditor`: form — name, emoji (free text input with a row of ~12 suggested emoji buttons), color (swatch row of the Metro palette), persona `<textarea>`, "make default" checkbox, delete button (hidden for default).
- `web/src/main.ts`:
  - Routes: `/profiles`, `/profiles/new`, `/profile/:id`, `/profile/:id/edit`.
  - Start page: profile picker strip above the command bar — one emoji button per profile, selected = filled; selection persisted as `localStorage.HERMES_PROFILE_ID`, default profile preselected; `runCommand(text, profileId)` threads it to `sendCommand`.
- `web/src/api.ts`: `Profile` type; `getProfiles`, `createProfile`, `updateProfile`, `deleteProfile`; `sendCommand(text, profileId?)`.
- `web/src/jobs.ts` / `history.ts`: when `job.profile` present, show its emoji next to status / prefer it on history tiles' meta line ("💻 coding").
- Seed `profiles` tile: key `profiles`, size `w`, sort 85, emoji 🎭 (both seed locations; shape map done in Phase 2).
- `web/src/styles.css`: `.profile-strip`, `.profile-pick`, `.profile-tile`, editor swatches.

### 5.5 Tests
- `server/tests/test_api.py`: profile CRUD; cannot delete default; setting a new default clears the old; `/api/command` without profile_id uses default and stores it on the job; `/api/jobs?profile_id=` filters; `agent_environment` unit test (persona env vars present/absent).
- `web/src/profiles.test.ts` (new): page renders tiles + new-tile; editor submits payload; focus view filters jobs.
- e2e: start page shows picker strip; selecting a profile persists across reload (stubbed `/api/profiles`).

---

## Phase 6 — Obsidian vault notes (req 4; notes part of 9) — **highest risk; do late, in one sitting**

### 6.1 Design
- **Layout**: folder-per-category — `vault/<category-slug>/<title-slug>-<id8>.md` (id8 = first 8 chars of the uuid, prevents slug collisions). Categories table stays as the taxonomy/color source; folders auto-created. Archive = move file to `vault/.archive/` (+ `archived: true` frontmatter).
- **Frontmatter schema** (YAML):
  ```yaml
  ---
  id: 3f2a9c1e-...      # full uuid; equals the API id, so /note/:id routes keep working
  title: oat milk brands
  category: errands
  tags: [groceries]
  created: 2026-06-12T14:03:00Z
  updated: 2026-06-12T14:03:00Z
  source_job_id: ...    # optional provenance
  archived: false
  ---
  body markdown…
  ```
- **Index/search**: full vault scan per request with an in-process cache keyed on directory mtimes (personal scale = hundreds of files; no DB index, no file watcher). Search = case-insensitive substring over title+body (same semantics as today's SQL LIKE).
- **Concurrency/sync safety**: atomic writes (`tempfile.NamedTemporaryFile` in same dir + `os.replace`); append = re-read → modify → atomic write; external edits always win (file is source of truth). **Skip** files matching `*.sync-conflict-*` and files whose frontmatter lacks `id`.
- **Config**: `OBSIDIAN_VAULT_PATH` env var (add to `.env.example` with comment). Unset = notes feature shows "connect vault" state.
- **Dependency**: `python-frontmatter` added to `server/pyproject.toml` and `mcp/pyproject.toml`.

### 6.2 New `server/app/vault.py`
```python
class VaultStore:
    def __init__(self, root: Path)
    def configured(self) -> bool
    def list_notes(self, category: str | None = None, include_archived=False) -> list[dict]
    def get(self, note_id: str) -> dict | None
    def create(self, title, body_md, category="inbox", tags=None, source_job_id=None) -> dict
    def update(self, note_id, *, title=None, body_md=None, category=None, tags=None) -> dict
    def append(self, note_id, text) -> dict           # blank line + text, bumps `updated`
    def move(self, note_id, category) -> dict          # moves file across folders
    def archive(self, note_id) -> dict
    def merge(self, source_id, target_id) -> dict      # append source body under "## merged: <title>", archive source
    def search(self, query, limit=20) -> list[dict]
```
Plus module-level `slugify(text)`, `atomic_write(path, content)`, `note_to_dict(...)`. Serialized shape: `{id, title, body_md, category, tags, archived, created_at, updated_at, source_job_id}` — **breaking change: `category_id` → `category` slug** (contained to 3 frontend files, see 6.5). Rename across folders on title/category change keeps the same `id` (filename is cosmetic; lookup is by frontmatter id via the index).

### 6.3 Server rewiring (`server/app/main.py`, `jobs.py`)
- All notes endpoints (`GET /api/notes`, `GET/PATCH /api/notes/{id}`, `POST .../archive`, `POST .../merge`) delegate to a module-level `get_vault()` (constructed from env, cached).
- `GET /api/notes` gains `q` (server-side search) and `category` params; response becomes `{notes, configured, warning}` mirroring the Vikunja-unconfigured pattern.
- `/api/vitals` notes count and `refresh_notes_tile` count from the vault (guard unconfigured → 0 + no crash).
- `GET /api/categories` unchanged (DB taxonomy drives folder names + UI colors).

### 6.4 Migration — new `server/app/migrate_notes.py`
Runnable as `uv run python -m app.migrate_notes`:
1. Requires `OBSIDIAN_VAULT_PATH`; loads categories map (id → slug) from DB.
2. For each non-archived DB note: skip if any vault file already has that frontmatter `id` (idempotent); else write `vault/<slug>/<title-slug>-<id8>.md` with full frontmatter, preserving original timestamps.
3. Prints report: migrated / skipped / errors. **Never deletes DB rows** — `notes` table and `Note` model stay as dormant legacy; rollback = unset `OBSIDIAN_VAULT_PATH`.

### 6.5 MCP (`mcp/hermes_home_mcp/`)
- **New `mcp/hermes_home_mcp/vault.py`**: minimal duplicated vault helpers (~150 lines: index scan, create, append, move, search) — consistent with how Vikunja logic is already duplicated there.
- `server.py`: rewrite `notes_create`, `notes_append`, `notes_move`, `notes_search`, `notes_list` to use the vault **keeping tool names and signatures identical** (e.g. `notes_create(title, body_md, category_slug="inbox", source_job_id=None)`); `notes_move` takes the category slug it already takes. `refresh_notes_tile` counts vault files. `categories_list`/`categories_create` unchanged. Reads `OBSIDIAN_VAULT_PATH` from env (already passed through by `agent_environment` — add it there in this phase).

### 6.6 Frontend
- `web/src/api.ts`: `Note` type — `category_id` → `category: string`, add `tags: string[]`; `getNotes({q, category})`.
- `web/src/notes.ts`: pivots filter by slug; detail editor's category `<select>` uses slugs (options from `/api/categories`); render tags via `chip()`; search box now calls the server `q` param (debounced 250ms) instead of client filtering; merge UI unchanged.
- `web/src/main.ts`: notes tile/page show `emptyState("📂", "connect your obsidian vault", warning)` when `configured: false`.

### 6.7 Skill update
`skills/categorize-notes/SKILL.md`: notes are markdown files in the Obsidian vault; categories = folders; tags go in frontmatter via the (unchanged) tools; dedupe rules unchanged (`notes_search` before create, prefer `notes_append`); never touch files outside the vault.

### 6.8 Tests
- **New `server/tests/test_vault.py`** (tmp_path vault): create/get/update round-trip; append preserves frontmatter; move changes folder, keeps id; archive → `.archive/`; merge appends + archives source; slug collision (two notes same title) → distinct files; conflict-file + id-less file skipped by index; search case-insensitive; `migrate_notes` idempotent (run twice → second run migrates 0).
- `server/tests/test_api.py`: notes endpoints against a tmp vault via env monkeypatch; unconfigured → `configured:false` without 500.
- `web/src/notes.test.ts` (new): slug pivots, tag chips, unconfigured state.
- e2e: notes flow against stubbed new response shape.

**Risk flags:** biggest phase. Mitigations: export-only idempotent migration; rollback = unset env var; MCP names/signatures preserved; server + MCP must flip together (both read the same env var) — hence "one sitting".

---

## Phase 7 — Codex chat polish + final cohesion pass (req 3; remainder of 2, 9)

### 7.1 Codex page → chat-style (`web/src/codex.ts`, `styles.css`)
- Run history rendered as a conversation feed, oldest→newest, auto-scrolled to bottom: each run = prompt bubble (right-aligned, accent border) followed by a reply bubble (status emoji + diff stat + duration; failed runs show stderr tail in a collapsible).
- Sticky bottom composer: textarea + send; effort toggle (low/med/high/xhigh) as compact segmented control; dangerous-mode checkbox tucked into a collapsible "details" row; workdir/git status behind a "workdir ▸" disclosure instead of always-on facts block.
- Auto-refresh the feed every 2s while any run is queued/running (reuse the polling pattern from `showCodexRun` in `main.ts`); running run's reply bubble shows a pulsing ⚙️.
- Tap a bubble → `/codex/:runId` detail (unchanged route).

### 7.2 Final cohesion sweep
- Consistent eyebrows on every page: `jobs / todos / notes / history / profiles / codex / approvals / settings` — replace oddballs (`agent canonical` in `todos.ts` ~line 20, `hermes native` in `notes.ts` ~line 7).
- Every list page uses `emptyState()` with a matching emoji; every date uses `shortDate`/`relativeDate`; every status uses `statusEmoji`.
- Nav bar: add 🕘 history glyph between home and settings (route `/history`).

### 7.3 Tests
- `web/src/codex.test.ts`: rewrite for feed + composer (submit payload includes effort + dangerous flag; feed renders run bubbles; polling triggers on running status).
- Expand `web/e2e/app.spec.ts` into a suite against stubbed API routes: start grid renders with **no gaps** (assert via tile bounding boxes tiling the grid rect), history page, profile picker select-and-send, todos project/label filters, codex composer send, notes vault states.

---

## Execution order & rationale

1 → 2 → 3 are additive with trivial migrations and immediate visible wins. 4 and 5 are independent of each other (4 first: the manage-todos skill is the highest-utility feature). 6 is last among features — the only phase with a data migration and an MCP behavior change. 7 is cosmetic and benefits from everything being settled.

## Risk register

| Risk | Mitigation |
|---|---|
| Vault migration loses notes | Export-only, idempotent, DB rows never deleted; rollback = unset `OBSIDIAN_VAULT_PATH` |
| Breaking the running agent's MCP contract | All tool changes additive or signature-preserving; new env vars ignored by old agents |
| Tile packer vs CSS breakpoints/flip animation | Packer is pure + unit-tested; manual check at <760px and ≥760px |
| Vikunja label API version quirks | `ensure_label` lists first; attach failures degrade to warnings |
| Seed/schema drift across the 4 mirrored locations | Treat the 4-place mirror as a checklist item in every schema-touching phase |
| Syncthing conflict files corrupt the index | Scanner skips `*.sync-conflict-*` and id-less files |

## Verification (after each phase)

1. `cd server && uv run pytest` — all existing + new tests green.
2. `cd web && npm test` (vitest) and `npx playwright test` (e2e).
3. Manual smoke with fallback agent: golden commands from `docs/upgrade.md` ("add buy oat milk to my todos", "file a note", "summarize today") → job done → page published → tiles refresh.
4. Phase-specific:
   - **P2**: no grid holes at both breakpoints; flip animation intact; emojis on all seeded tiles.
   - **P3**: `/history` shows heuristic tiles for pre-upgrade jobs and agent-set ones for new jobs after the skill update.
   - **P4**: todo created via command lands in the right Vikunja project with labels/priority — verify in both the Hermes UI and the Vikunja web UI.
   - **P5**: create a profile in the UI, run a command with it; confirm `HERMES_HOME_PROFILE_*` reaches the agent (test script dumping env) and the job records the profile.
   - **P6**: `uv run python -m app.migrate_notes` (run twice — second run migrates 0); open the vault in Obsidian; edit a file in Obsidian and confirm the app reflects it; agent `notes_create` produces a valid vault file.
   - **P7**: codex chat sends a run, feed auto-refreshes while running, diff stat appears on completion.
5. Update docs: `docs/upgrade.md` golden commands (notes category slug), `docs/HERMES_SERVER_INSTALL.md` (OBSIDIAN_VAULT_PATH, profile env vars, new skills to pin: manage-todos), `.env.example` (OBSIDIAN_VAULT_PATH).
