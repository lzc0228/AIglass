# Agent Persistence And Task-21 Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build durable task/process persistence under `plan/`, map `TODO (2).md` into 21 tasks, and complete task #21 by adding realtime local log persistence in `app_main.py`.

**Architecture:** Add a lightweight process-state layer (`plan/AGENT.MD`, `plan/task.json`, `plan/progress.txt`) and a low-intrusion runtime tee logger in `app_main.py` that duplicates stdout/stderr to timestamped files under `log/`. Keep runtime behavior unchanged except file logging side effect.

**Tech Stack:** Python 3, FastAPI app entrypoint, JSON task state, plain text progress journal, git local commits.

---

### Task 1: Create Persistent Agent Workflow Files

**Files:**
- Create: `plan/AGENT.MD`
- Create: `plan/task.json`
- Create: `plan/progress.txt`
- Source reference: `TODO (2).md`

**Step 1: Write the failing check (state files do not exist yet)**

```bash
test -f plan/AGENT.MD && test -f plan/task.json && test -f plan/progress.txt
```

Expected: non-zero exit code before file creation.

**Step 2: Create `plan/AGENT.MD` minimal deterministic workflow**

```markdown
# Agent Workflow (Persistent)
1) Resume from `plan/task.json`
2) Pick one `passes=false` task (prefer `status=in_progress`)
3) Implement + verify
4) Append `plan/progress.txt`
5) Update `plan/task.json`
6) Commit exactly one task
```

**Step 3: Create `plan/task.json` with 21 tasks mapped from `TODO (2).md`**

```json
{
  "project": "IROS",
  "source": "TODO (2).md",
  "tasks": [
    {"id": 1, "title": "...", "status": "pending", "passes": false},
    ...
    {"id": 21, "title": "Persist app_main output logs locally", "status": "in_progress", "passes": false}
  ]
}
```

**Step 4: Create `plan/progress.txt` with entry template**

```text
# Progress Log
## YYYY-MM-DD HH:MM - Task #N
- What changed
- Verification
- Commit
```

**Step 5: Re-run existence and parse checks**

Run:

```bash
test -f plan/AGENT.MD && test -f plan/task.json && test -f plan/progress.txt
python - <<'PY'
import json
with open('plan/task.json','r',encoding='utf-8') as f:
    data=json.load(f)
assert len(data['tasks'])==21
print('task.json OK')
PY
```

Expected: all checks pass, prints `task.json OK`.

---

### Task 2: Implement Task #21 Runtime Log Persistence In `app_main.py`

**Files:**
- Modify: `app_main.py`
- Output directory: `log/`

**Step 1: Write failing smoke expectation**

Run:

```bash
python -m py_compile app_main.py
```

Expected: currently compiles, but no guaranteed startup log file with tee behavior.

**Step 2: Add tee logger utility near startup code**

```python
class _TeeStream:
    def write(self, data): ...
    def flush(self): ...

def _init_realtime_file_logging():
    # env: AIGLASS_FILE_LOG=1, AIGLASS_FILE_LOG_DIR=log
    # create log/app_main-YYYYMMDD_HHMMSS.log
    # replace sys.stdout/sys.stderr with tee wrappers
```

**Step 3: Invoke logger init once before runtime startup prints**

```python
_init_realtime_file_logging()
```

**Step 4: Keep fail-safe behavior**

```python
try:
    _init_realtime_file_logging()
except Exception:
    pass  # do not break app startup
```

**Step 5: Verify syntax**

Run:

```bash
python -m py_compile app_main.py
```

Expected: PASS.

---

### Task 3: Verify Runtime Logging Behavior

**Files:**
- Runtime artifact: `log/app_main-*.log`

**Step 1: Start app briefly**

Run:

```bash
python app_main.py
```

Stop after startup messages appear.

**Step 2: Verify log file created and appended**

Run:

```bash
ls -t log/app_main-*.log | head -n 1
tail -n 30 "$(ls -t log/app_main-*.log | head -n 1)"
```

Expected: latest file exists and contains startup output.

---

### Task 4: Close Loop In Persistence State And Commit

**Files:**
- Modify: `plan/task.json` (task #21 -> done)
- Modify: `plan/progress.txt` (append actual run results)
- Commit target files:
  - `plan/AGENT.MD`
  - `plan/task.json`
  - `plan/progress.txt`
  - `app_main.py`

**Step 1: Append progress entry**

```text
## 2026-02-26 HH:MM - Task #21
- Implemented realtime tee logging in app_main.py
- Verified py_compile and runtime log creation
- Updated task status
```

**Step 2: Mark task #21 complete**

```json
{"id":21,"status":"done","passes":true}
```

**Step 3: Final verification**

Run:

```bash
python -m py_compile app_main.py
python - <<'PY'
import json
with open('plan/task.json','r',encoding='utf-8') as f:
    d=json.load(f)
t=[x for x in d['tasks'] if x['id']==21][0]
assert t['passes'] is True and t['status']=='done'
print('task21 done')
PY
```

Expected: PASS and prints `task21 done`.

**Step 4: Commit**

```bash
git add plan/AGENT.MD plan/task.json plan/progress.txt app_main.py
git commit -m "feat(plan): add persistent workflow and complete task #21 logging"
```

Expected: one local commit for one completed task.
