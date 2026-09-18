# Diagnosis reference

## Purpose

Use this reference only when the default cleanup script fails, the database schema changes, or archived runs remain visible after restart.

## Known state layers

### Automation definition

Typical path:

```text
~/.codex/automations/<automation-id>/automation.toml
```

Important fields include `id`, `name`, `status`, `rrule`, target, and execution environment.

Repeated sidebar rows do **not** prove repeated automation definitions.

### Session index

Typical path:

```text
~/.codex/session_index.jsonl
```

Historical scheduled runs can appear as distinct rows with the same `thread_name` and different UUIDs. Use `updated_at` to choose the newest run to keep.

### Thread state DB

Typical path:

```text
~/.codex/state_5.sqlite
```

The `threads` table has been observed with fields such as:

- `id`
- `rollout_path`
- `archived`
- `archived_at`
- `name`
- `thread_source`
- `project_id`

A stale run can already have `archived=1` and an `archived_sessions/...jsonl` rollout path while still appearing in the Desktop sidebar.

### Desktop app DB

Observed candidates:

```text
~/.codex/sqlite/codex.db
~/.codex/sqlite/codex-dev.db
```

The script selects the database that contains both `automation_runs` and `local_thread_catalog`.

Observed `automation_runs.status` values include:

```text
IN_PROGRESS
PENDING_REVIEW
ACCEPTED
ARCHIVED
```

The Desktop app's own archive side effect has been observed to transition a matching automation run to `ARCHIVED` and may set `archived_reason` to `auto`.

### Local sidebar catalog

The Desktop app has been observed to maintain a `local_thread_catalog`. Its normal archived-thread handling removes the archived thread from that catalog and bumps a catalog revision. If a thread was archived outside the full Desktop archive flow, the catalog can remain stale.

## Why `codex archive <UUID>` may be insufficient

The bundled Codex CLI can successfully archive a saved session and update thread state, but a separate Electron/Desktop state layer may still retain:

- an `automation_runs` row in `PENDING_REVIEW`;
- a `local_thread_catalog` row.

That mismatch explains the failure mode where:

1. the archived rollout file exists;
2. `threads.archived=1` is correct;
3. the sidebar still shows the old scheduled run after restart.

The cleanup script reconciles these layers only after exact-title validation and backups.

## Schema drift procedure

If the script stops with a schema-change error:

1. Do not force the write.
2. Inspect table names and `PRAGMA table_info(...)` read-only.
3. Inspect the currently bundled Codex app's app-server JSON schema if relevant.
4. Prefer an official CLI or app-server archive API when available.
5. If Desktop-specific side effects remain necessary, derive them from current app behavior/code before editing any DB.
6. Add a regression test before updating the script.

## Non-goals

This workflow does not:

- delete the recurring schedule;
- permanently delete archived chats;
- bypass authentication;
- scrape ChatGPT account data;
- modify unrelated Codex project history;
- rely on screen coordinates.
