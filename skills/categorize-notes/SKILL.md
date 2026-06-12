---
name: categorize-notes
description: Categorize Hermes Home notes with dedupe and cap rules.
---

# Categorize Notes

Use this skill when a command stores memory, reference facts, household details, or summaries as notes.

Hermes Home notes are markdown files in the configured Obsidian vault. Categories map to vault folders, and durable labels belong in YAML frontmatter `tags`. Never read or write files outside the vault; use the notes MCP tools so the app, tile counts, and Obsidian files stay aligned.

## Categories

Prefer existing categories from `categories_list`. The starter taxonomy is:

- `inbox`: uncertain or needs review.
- `home`: household facts, supplies, maintenance, appliance details.
- `errands`: shopping, pickups, and location-based tasks.
- `health`: appointments, care notes, wellness reminders.
- `reference`: stable facts that should be retrieved later.

Create a new category only when the note will clearly recur and none of the starter categories fit.

## Dedupe Rules

- Normalize title and body before comparing: trim whitespace, lowercase, collapse repeated spaces.
- Prefer updating context through metadata instead of creating near-duplicates.
- Search with `notes_search` before writing. If an existing note already captures the fact, update it with `notes_append` instead of creating a duplicate.
- If two facts are related but independently useful, store separate notes with precise titles.

## Cap Rules

- Store at most five notes from a single command unless the user explicitly asks for a larger import.
- Keep each note focused on one reusable fact.
- Keep titles under 80 characters.
- Keep bodies concise; long source text belongs in a generated page, with only the durable summary saved as a note.
- Use `inbox` when confidence is low instead of overfitting a category.

## Tags And Metadata

Prefer one to three lowercase tags when they help retrieval later, for example `groceries`, `hvac`, `doctor`, or `warranty`. Reuse obvious existing wording from related notes. Do not invent a broad tag for one isolated note.

Do not put secrets, tokens, or private credentials in note bodies, tags, or frontmatter.

## Completion Checklist

- Categories were read with `categories_list` before choosing a category.
- Duplicate content was avoided.
- No more than five notes were created with `notes_create` from the command.
- The notes tile was refreshed or marked stale.
- A generated page summarizes what was saved.
