---
name: keep-tiles-fresh
description: Refresh Hermes Home tiles after database state changes.
---

# Keep Tiles Fresh

Use this skill after any MCP tool call or agent action that changes user-visible state. Tiles are the first screen of Hermes Home, so stale counts are treated as a product bug.

## Tile Keys

- `jobs`: current command execution state.
- `todos`: open todo count and last completion hint.
- `calendar`: upcoming calendar status and write-approval state.
- `notes`: stored note count and category status.
- `approvals`: pending approval count.

## Update Rules

- After creating or completing todos, refresh `todos`.
- After creating or deduping notes, refresh `notes`.
- After requesting or deciding approvals, refresh `approvals`.
- After requesting a calendar write, refresh both `calendar` and `approvals`.
- During long work, mark the affected tile `working`; after the write, mark it `fresh`.
- If a read fails or a count cannot be trusted, mark the tile `stale` with a short back-face explanation.

## Front And Back Payloads

Use small JSON objects only. The web client should be able to render them without special casing.

Recommended front payload:

```json
{"line":"open","count":3}
```

Recommended back payload:

```json
{"line":"last changed"}
```

## Count Discipline

- Do not guess counts.
- Count from the database when possible.
- Keep count fields numeric.
- Keep line fields under 40 characters.
- Keep labels stable; change tile content, not tile identity.

## Completion Checklist

- All affected tiles were refreshed or explicitly marked stale.
- The job event log mentions the tile refresh for state-changing work.
- The tile payload contains only JSON-safe strings, numbers, booleans, arrays, and objects.

