---
name: codex-scheduled-task-cleanup
description: Diagnose and clean up stale or duplicate Codex Desktop scheduled-task run entries on macOS when one recurring schedule creates many old sidebar threads. Use when Codex/ChatGPT Desktop shows repeated historical scheduled-run chats, archived runs remain visible after restart, or a user wants to keep only the newest N run threads without deleting the recurring schedule. Operate only on exact-title matches, prefer dry-run first, preserve archived sessions, back up SQLite state before writes, and verify the active schedule remains intact.
---

# Codex Scheduled Task Cleanup

Use this workflow for the macOS Codex experience embedded in ChatGPT Desktop when **one recurring automation** produces many historical run threads that stay visible in the project sidebar.

## Core rule

Treat these as three separate objects:

1. **Automation definition** — the recurring schedule. Do not delete it unless the user explicitly asks.
2. **Run thread/session** — one chat/session created by a schedule execution.
3. **Desktop sidebar/inbox state** — Electron-local state that can keep an already archived run visible.

A successful cleanup must archive the old run thread **and** reconcile the Desktop-side run/catalog state. Moving rollout files alone may not remove the sidebar entry.

## Workflow

### 1. Confirm the problem before writing

Inspect, read-only:

- `$CODEX_HOME/automations/*/automation.toml`
- `$CODEX_HOME/session_index.jsonl`
- `$CODEX_HOME/state_5.sqlite`
- `$CODEX_HOME/sqlite/codex.db` or `$CODEX_HOME/sqlite/codex-dev.db`

Determine:

- the exact automation name/title;
- whether there is only one active automation definition;
- how many historical sessions share that exact title;
- which session is newest;
- whether old threads are already `archived=1` in `state_5.sqlite`;
- whether matching rows remain `PENDING_REVIEW` in `automation_runs`;
- whether matching rows remain in `local_thread_catalog`.

Never infer that repeated sidebar rows mean repeated schedules. Prove it from the automation definition first.

### 2. Use the bundled cleanup script in dry-run mode

Run:

```bash
python3 scripts/cleanup_codex_scheduled_runs.py \
  --title "<exact automation title>" \
  --automation-id "<automation id>"
```

The script keeps the newest matching session by default and prints what would be archived. It performs no writes without `--apply`.

If the user's automation id is unknown, omit `--automation-id` for discovery, then verify the automation definition manually before applying changes.

### 3. Apply only after exact-match validation

Run:

```bash
python3 scripts/cleanup_codex_scheduled_runs.py \
  --title "<exact automation title>" \
  --automation-id "<automation id>" \
  --apply
```

The script must:

- back up the Codex app DB and thread state DB;
- keep the newest matching session untouched;
- use the Codex CLI `archive <thread-id>` for non-archived stale threads;
- set stale automation-run rows to `ARCHIVED` with `archived_reason='auto'` when the current schema supports it;
- remove stale local sidebar catalog rows;
- bump the catalog revision when rows are removed;
- verify the kept thread was not archived;
- verify stale rows no longer remain visible in the local catalog.

Do not delete `archived_sessions`, the automation definition, or unrelated sessions.

### 4. Refresh the Desktop app

After a successful repair, fully quit and reopen ChatGPT Desktop so the renderer reloads the corrected local catalog.

If old rows still appear, do not repeatedly mutate data. Re-inspect the current schema and app state first.

### 5. Optional recurring cleanup

If each schedule execution creates a new standalone thread and the user wants only the newest run visible, install a LaunchAgent a few minutes after each scheduled run:

```bash
python3 scripts/install_launchagent.py \
  --cleanup-script "$(pwd)/scripts/cleanup_codex_scheduled_runs.py" \
  --title "<exact automation title>" \
  --automation-id "<automation id>" \
  --times "06:10,11:10,16:10"
```

Choose times based on the user's actual schedule. Do not hard-code the example times unless they match the real automation.

## Safety constraints

- Default to dry-run.
- Match the title exactly; never use a broad substring for writes.
- Keep at least one session unless the user explicitly requests otherwise.
- Create SQLite backups before modifying app state.
- Abort on schema drift instead of guessing column names.
- Do not directly edit `session_index.jsonl` unless a future version makes that necessary and the behavior is first proven with read-only evidence.
- Do not expose auth tokens, cookies, account identifiers, or unrelated project data.
- Do not use fixed-coordinate UI automation for destructive operations.
- Do not claim success until the final sidebar state is verified after app restart.

## Version-sensitive details

The current implementation relies on local Codex Desktop structures observed on macOS, including `state_5.sqlite`, `automation_runs`, and `local_thread_catalog`. These are internal implementation details and may change. Read [references/diagnosis.md](references/diagnosis.md) before patching the script for a new Codex release. For Chinese-language troubleshooting, use [references/diagnosis.zh-CN.md](references/diagnosis.zh-CN.md).
