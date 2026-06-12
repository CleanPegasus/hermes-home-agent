---
name: deliver-as-page
description: Publish Hermes results as sanitized pages instead of chat replies.
---

# Deliver As Page

Use this skill whenever Hermes completes a user command in Hermes Home. The durable output is a page stored through the Hermes Home MCP tool surface.

## Rules

- Do not finish with a conversational answer when a page can be published.
- Publish exactly one primary page for the job with `pages_publish`.
- Keep the page self-contained: no scripts, external assets, remote fonts, iframes, or network URLs.
- Do not use inline event handlers such as `onclick`.
- Use semantic HTML: `main`, `section`, `h1`, `h2`, `p`, `ul`, `ol`, `table`, `button`.
- Put actions on buttons with `data-action` and optional JSON `data-payload`.
- Keep copy concise. The page should show the result, the reason it matters, and the next action.
- Log steps with `log_job_event` before long reads, writes, approvals, or page publication.

## Page Shape

Start from `template.html` when possible. Replace the title, summary, sections, and actions. Keep the CSS local to the page.

Required content:

- A clear `h1`.
- A short status line.
- One or more useful content sections.
- A final action area when the workflow created something actionable.

## Action Buttons

Action buttons must be deterministic and safe for the app server to execute.

Examples:

```html
<button type="button" data-action="todos.complete" data-payload='{"todo_id":123}'>mark done</button>
<button type="button" data-action="approvals.open" data-payload='{"approval_id":45}'>review approval</button>
```

Do not invent action names unless the app server already supports them. If an action would require external writes, create an approval first and point the page at that approval.

## Completion Checklist

- Relevant state has been written through MCP tools.
- Tiles have been refreshed or marked stale.
- The page has no script or external-load behavior.
- The page includes action buttons only for supported actions.
- `pages_publish` was called with the active `HERMES_HOME_JOB_ID`.
