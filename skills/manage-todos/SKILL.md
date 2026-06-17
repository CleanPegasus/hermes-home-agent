---
name: manage-todos
description: Use when a command creates or edits a todo in Hermes Home through Todoist-backed tools.
---

# Manage Todos

Use this skill for any command that creates or edits a todo. Todos are backed by
the Todoist cloud API; tasks belong to projects and carry plain-name labels.

## Procedure

1. Call `todos_projects_list` and `todos_labels_list` before choosing where a todo belongs.
2. Pick the project whose name best matches the topic. Groceries, shopping, errands, pickups, and repairs belong in the closest errands/home project. Work topics belong in the closest work project. If nothing fits, use the default project (the Todoist Inbox when no default is set).
3. Reuse labels case-insensitively. Labels are plain names (no leading symbol). Create at most one new label per todo, lowercase and singular.
4. Set due dates the natural way. Prefer passing the user's phrasing as `due_string` (for example "tomorrow 5pm", "next monday"); Todoist parses it in the user's timezone. When you already have an exact value, pass `due_date` (YYYY-MM-DD) for all-day or `due_datetime` (RFC3339) for a timed due date instead.
5. Map priority on Todoist's 1-4 scale where 4 is highest/urgent: urgent/asap = 4, important = 3, normal = 2 (or omit), someday/maybe = 1.
6. Call `job_set_summary` with a concise summary of the created or updated todo. Do not call `pages_publish` for todo-only commands.

## Guardrails

- Never move an existing todo between projects unless the user asks.
- Never delete labels.
- Never create multiple near-duplicate labels for one todo.
- If project or label metadata is unavailable, create the todo in the default project and say what could not be read.
