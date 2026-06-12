---
name: manage-todos
description: Use when a command creates or edits a todo in Hermes Home through Vikunja-backed tools.
---

# Manage Todos

Use this skill for any command that creates or edits a todo.

## Procedure

1. Call `todos_projects_list` and `todos_labels_list` before choosing where a todo belongs.
2. Pick the project whose title best matches the topic. Groceries, shopping, errands, pickups, and repairs belong in the closest errands/home project. Work topics belong in the closest work project. If nothing fits, use the default project.
3. Reuse labels case-insensitively. Create at most one new label per todo, lowercase and singular.
4. Convert natural-language due dates into RFC3339 in the user's timezone before passing `due_at`.
5. Map priority this way: urgent/asap = 5, important = 4, normal = omit or 0, someday/maybe = 1.
6. Publish a page that states the project, labels, due date, and priority that were set so the user can verify the result at a glance.

## Guardrails

- Never move an existing todo between projects unless the user asks.
- Never delete labels.
- Never create multiple near-duplicate labels for one todo.
- If project or label metadata is unavailable, create the todo in the default project and say what could not be read.
