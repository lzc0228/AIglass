# Agent Workflow (Persistent)

This folder is the single source of execution state for long-running work.

## Session Start (Required)

1. Read `plan/task.json`.
2. If any task has `status: "in_progress"` and `passes: false`, resume it first.
3. Otherwise pick one task with `passes: false` (highest priority / lowest id).

## Execution Loop (One Task At A Time)

1. Implement only the selected task scope.
2. Run verification commands listed in that task.
3. Append an entry to `plan/progress.txt` with timestamp, changes, and verification.
4. Update task state in `plan/task.json`.
5. Commit exactly that task's changes in one local commit.

## State Rules

- `status`: `pending | in_progress | done | blocked`
- `passes`: `true` only when all acceptance/verification checks are satisfied.
- If blocked, set `status: "blocked"` and keep `passes: false`.

## Recovery Rules

- Never delete old progress entries.
- Never remove tasks from `plan/task.json`.
- If session is interrupted, recovery always starts from `task.json` + latest `progress.txt` entry.

