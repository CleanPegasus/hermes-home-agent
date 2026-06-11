---
name: categorize-notes
description: Categorize Hermes Home notes with dedupe and cap rules.
---

# Categorize Notes

Use this skill when a command stores memory, reference facts, household details, or summaries as notes.

## Categories

Prefer existing categories from `list_categories`. The starter taxonomy is:

- `inbox`: uncertain or needs review.
- `home`: household facts, supplies, maintenance, appliance details.
- `errands`: shopping, pickups, and location-based tasks.
- `health`: appointments, care notes, wellness reminders.
- `reference`: stable facts that should be retrieved later.

Create a new category only when the note will clearly recur and none of the starter categories fit.

## Dedupe Rules

- Normalize title and body before comparing: trim whitespace, lowercase, collapse repeated spaces.
- Prefer updating context through metadata instead of creating near-duplicates.
- If `add_note` reports `deduped: true`, do not create another note for the same fact.
- If two facts are related but independently useful, store separate notes with precise titles.

## Cap Rules

- Store at most five notes from a single command unless the user explicitly asks for a larger import.
- Keep each note focused on one reusable fact.
- Keep titles under 80 characters.
- Keep bodies concise; long source text belongs in a generated page, with only the durable summary saved as a note.
- Use `inbox` when confidence is low instead of overfitting a category.

## Metadata

Useful metadata keys:

```json
{
  "confidence": "high",
  "source_command": "original user command",
  "entities": ["filter", "hallway"],
  "expires_at": null
}
```

Do not put secrets, tokens, or private credentials in note metadata.

## Completion Checklist

- Categories were read before choosing a category.
- Duplicate content was avoided.
- No more than five notes were created from the command.
- The notes tile was refreshed or marked stale.
- A generated page summarizes what was saved.

