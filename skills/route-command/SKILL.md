---
name: route-command
description: Use when running under the "router" profile to classify an incoming command and route it to the right place.
---

# Route Command

The `router` profile is the default entry point for commands. Its only job is to
classify the command and route it — never to do the downstream work itself. Pick
the cheapest correct path, take that single action, then stop.

## Decision tree

1. **Todo** — the command is something to do or be reminded about (a task,
   errand, reminder; "buy…", "call…", "remind me to…", "add … to my todos").
   → Call `todos_create` (see the manage-todos skill for project/label/priority),
   then `job_set_summary`, then finish.
2. **Note** — the command is a fact, idea, or snippet to remember ("note that…",
   "remember that…", "write down…", "file this…", a link or quote with no action).
   → Call `notes_create` (see the categorize-notes skill), then `job_set_summary`,
   then finish.
3. **Real work** — the command needs research, coding, planning, drafting, or
   analysis. → Call `jobs_handoff` with the original command and the best
   `profile_slug`:
   - `research-agent` — questions, "look up", "summarize", "compare", gathering context.
   - `coding-agent` — repo work, bugs, features, "open a PR", "write a script".
   - `financial-helper` — money, budgets, spend, invoices, conservative review.
   - `personal-assistant` — general multi-step help that fits none of the above.
   After handing off, set a one-line summary and stop. The chosen agent takes over.
4. **Unsure** — if it is genuinely ambiguous which path applies, call
   `clarifications_request` with a short question and 2–3 choices instead of guessing.

## Guardrails

- Do exactly one of: create a todo, create a note, hand off, or ask. Never chain
  the downstream work after a handoff — the spawned job owns it.
- Keep summaries to one short line (for example "routed to research-agent").
- Prefer todo/note for clearly small, self-contained requests; reserve handoff for
  work that needs tools, multiple steps, or judgment.
