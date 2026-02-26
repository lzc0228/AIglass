# Agent Persistence And Task Tracking Design

## Summary

This design adds a persistent execution process under `plan/` to avoid session-loss progress drift and to support deterministic one-task-at-a-time local commits.

Deliverables:
- `plan/AGENT.MD`
- `plan/task.json`
- `plan/progress.txt`
- Task #21 implementation in `app_main.py`: realtime local log persistence

## Goals

- Persist agent workflow state across interrupted sessions.
- Convert `TODO (2).md` into 21 explicit, traceable tasks.
- Enforce a stable loop: pick one incomplete task, implement, verify, record, commit.
- Complete one initial task and commit to local git to prove the workflow.

## Constraints

- Rule/strategy-first implementation; no heavy model replacement.
- Keep changes low-risk and minimally invasive.
- Local-only persistence; no external database dependency.
- Keep existing runtime behavior unchanged except logging persistence addition.

## Architecture

### 1) Process State Layer (`plan/`)

#### `plan/AGENT.MD`
- Defines mandatory workflow steps:
  - resume from `task.json`
  - select one task (`passes=false`)
  - implement
  - run verification
  - append `progress.txt`
  - update task status
  - commit once for that task
- Defines blocking behavior: do not mark complete when blocked.
- Defines recovery rule: prioritize `status=in_progress` when present.

#### `plan/task.json`
- Source of truth for task execution state.
- Contains 21 tasks mapped from `TODO (2).md` (one-to-one).
- Per-task fields:
  - `id`
  - `title`
  - `source_line`
  - `description`
  - `acceptance`
  - `verification`
  - `status` (`pending|in_progress|done|blocked`)
  - `passes` (`true|false`)
  - `dependencies`
- Initial execution target: task `21` (local log persistence).

#### `plan/progress.txt`
- Append-only execution journal.
- Entry template:
  - timestamp
  - task id/title
  - files changed
  - verification commands and outcomes
  - commit hash
  - notes/blockers

### 2) Runtime Logging Layer (Task #21)

#### Scope
- Add realtime log file persistence for existing `app_main.py` output.

#### Design
- Initialize a file logger stream at startup:
  - default dir: `log/`
  - file pattern: `app_main-YYYYMMDD_HHMMSS.log`
- Tee mode:
  - keep terminal output
  - simultaneously write `stdout` and `stderr` to file
- Config knobs:
  - enable/disable via env var (default enabled)
  - optional custom log dir
- Fail-safe:
  - if file setup fails, continue runtime with terminal output only.

## Data Flow

### Session Recovery Flow
1. Read `plan/task.json`.
2. If any task is `in_progress`, resume it.
3. Otherwise select the first/highest-priority `passes=false` task.
4. Execute and verify.
5. Append `plan/progress.txt`.
6. Update task state in `plan/task.json`.
7. Commit code + `plan/*` updates for that task.

### Runtime Log Flow
1. App startup triggers log tee initialization.
2. `print()` and uncaught traceback output go to:
   - terminal
   - current session log file
3. Log file is appended continuously until process exits.

## Error Handling

- Missing `plan/` files:
  - create with safe defaults.
- Invalid `task.json`:
  - fail fast for editing path; keep runtime path unaffected.
- Log file initialization failure:
  - emit warning to terminal, do not stop application.
- Duplicate/inconsistent task statuses:
  - prioritize explicit `in_progress`, otherwise treat `passes=false` as executable.

## Testing Plan

### Persistence Files
- Validate presence and readability:
  - `plan/AGENT.MD`
  - `plan/task.json`
  - `plan/progress.txt`
- Validate `task.json` schema consistency and 21-task count.

### Task #21 Logging
- `python -m py_compile app_main.py`
- Start app briefly and verify:
  - log file is created under `log/`
  - terminal output still visible
  - new lines are appended in near-realtime

## Rollout Plan

1. Add this design document and commit.
2. Create `plan/AGENT.MD`, `plan/task.json`, `plan/progress.txt`.
3. Implement task #21 in `app_main.py`.
4. Verify and record results in `plan/progress.txt`.
5. Mark task #21 as done in `plan/task.json`.
6. Create one local commit for task #21 changes.

## Out Of Scope For First Commit

- Completing tasks #1-#20.
- Large refactors across navigation pipelines.
- New external dependencies.
