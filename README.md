# Codex Scheduled Task Cleanup

[简体中文](README.zh-CN.md)

A reusable ChatGPT Skill and macOS utility for diagnosing and cleaning up **stale historical Codex scheduled-task run threads** that remain visible in the ChatGPT/Codex project sidebar.

## The problem

A single recurring Codex automation can legitimately create a new local session every time it runs. Over time, the project sidebar may show many rows with the same title even though **only one recurring schedule exists**.

In the failure mode this project targets, archiving the old session file alone is not enough. ChatGPT/Codex Desktop can still retain stale automation-run and sidebar-catalog state, so old rows remain visible even after the app is restarted.

## What this project fixes

The workflow separates three different layers:

1. **Automation definition** — the recurring schedule itself.
2. **Run thread/session** — one local session created by one execution.
3. **Desktop state** — automation-review and sidebar-catalog records used by the app UI.

The cleanup script:

- defaults to **dry-run**;
- matches one exact thread title;
- keeps the newest run by default;
- backs up SQLite state before writes;
- archives stale sessions with the Codex CLI;
- reconciles stale `automation_runs` and `local_thread_catalog` rows;
- verifies the newest run remains untouched;
- is idempotent.

## Requirements

- macOS
- ChatGPT Desktop with Codex local sessions
- Python 3
- Codex CLI bundled with ChatGPT Desktop, or another `codex` binary available in `PATH`

## Quick start

### 1. Dry run first

```bash
python3 scripts/cleanup_codex_scheduled_runs.py \
  --title "My scheduled task" \
  --automation-id "my-automation-id"
```

### 2. Apply after checking the preview

```bash
python3 scripts/cleanup_codex_scheduled_runs.py \
  --title "My scheduled task" \
  --automation-id "my-automation-id" \
  --apply
```

Then fully quit and reopen ChatGPT Desktop.

### 3. Optional automatic cleanup

Schedule cleanup a few minutes after each recurring task run:

```bash
python3 scripts/install_launchagent.py \
  --cleanup-script "$(pwd)/scripts/cleanup_codex_scheduled_runs.py" \
  --title "My scheduled task" \
  --automation-id "my-automation-id" \
  --times "06:10,11:10,16:10"
```

Use times that match your actual automation schedule. The example above assumes runs around 06:00, 11:00 and 16:00.

## Safety design

This project intentionally does **not** permanently delete chats or schedules.

It uses:

- exact-title matching;
- optional automation-ID verification;
- a minimum keep count of 1;
- SQLite backups before writes;
- schema checks that stop on unexpected database changes;
- post-write verification;
- no fixed-coordinate UI automation;
- no authentication-token or cookie extraction.

The local Codex database structures used here are implementation details and can change across releases. Always run dry-run first after a Codex/ChatGPT Desktop update.

## Why `codex archive <UUID>` alone may not be enough

In the stale-sidebar case, the run thread can already be correctly archived while the Desktop app still has:

- an `automation_runs` row in `PENDING_REVIEW`; and/or
- a `local_thread_catalog` row for that archived thread.

The app UI can therefore keep showing the old run. This project reconciles those extra layers after validating the exact target.

See [references/diagnosis.md](references/diagnosis.md) for the technical explanation.

## Install as a ChatGPT Skill

Upload the packaged `skill.zip` to ChatGPT Skills, or use this repository as the source for a personal Skill.

## Important compatibility note

This project was built from observed behavior of Codex inside ChatGPT Desktop on macOS in September 2026. Internal schemas can change. The script intentionally fails closed instead of guessing when expected tables or columns are missing.

## License

MIT. See [LICENSE](LICENSE).
