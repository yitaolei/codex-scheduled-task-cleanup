#!/usr/bin/env python3
"""Safely archive stale Codex scheduled-run sessions while keeping the newest N.

Default mode is dry-run. Use --apply to make changes.
This script is intentionally conservative and only operates on exact title matches.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Session:
    updated_at: str
    thread_id: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Archive stale Codex scheduled-task sessions and remove stale sidebar catalog entries."
    )
    p.add_argument("--title", required=True, help="Exact thread title to match")
    p.add_argument("--automation-id", help="Optional exact automation id safety check")
    p.add_argument("--keep", type=int, default=1, help="Number of newest matching sessions to keep (default: 1)")
    p.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    p.add_argument("--codex-bin", type=Path, help="Codex CLI path; auto-detected when omitted")
    p.add_argument("--apply", action="store_true", help="Apply changes. Without this flag, dry-run only")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return p.parse_args()


def find_codex_bin(explicit: Path | None) -> Path:
    if explicit:
        return explicit
    bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if bundled.exists():
        return bundled
    found = shutil.which("codex")
    if found:
        return Path(found)
    raise RuntimeError("Could not find Codex CLI. Pass --codex-bin explicitly.")


def load_sessions(index: Path, title: str) -> list[Session]:
    if not index.exists():
        raise RuntimeError(f"Missing session index: {index}")
    latest_by_id: dict[str, str] = {}
    for raw in index.read_text(errors="replace").splitlines():
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if item.get("thread_name") != title:
            continue
        thread_id = item.get("id")
        updated_at = item.get("updated_at") or ""
        if isinstance(thread_id, str) and thread_id:
            if thread_id not in latest_by_id or updated_at > latest_by_id[thread_id]:
                latest_by_id[thread_id] = updated_at
    return sorted(
        (Session(updated_at=v, thread_id=k) for k, v in latest_by_id.items()),
        key=lambda s: (s.updated_at, s.thread_id),
        reverse=True,
    )


def connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "select 1 from sqlite_master where type='table' and name=?", (name,)
    ).fetchone() is not None


def find_app_db(codex_home: Path) -> Path:
    candidates = [
        codex_home / "sqlite" / "codex.db",
        codex_home / "sqlite" / "codex-dev.db",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            con = connect_ro(p)
            ok = table_exists(con, "automation_runs") and table_exists(con, "local_thread_catalog")
            con.close()
            if ok:
                return p
        except sqlite3.Error:
            pass
    raise RuntimeError("Could not find Codex app DB with automation_runs + local_thread_catalog tables")


def validate_schema(app_db: Path, state_db: Path, automation_id: str | None, title: str) -> None:
    if not state_db.exists():
        raise RuntimeError(f"Missing state DB: {state_db}")
    app = connect_ro(app_db)
    state = connect_ro(state_db)
    try:
        app_cols = {r[1] for r in app.execute("pragma table_info(automation_runs)")}
        required_app = {"thread_id", "automation_id", "status", "thread_title", "updated_at", "archived_reason"}
        if not required_app.issubset(app_cols):
            raise RuntimeError(f"automation_runs schema changed; missing {sorted(required_app - app_cols)}")
        cat_cols = {r[1] for r in app.execute("pragma table_info(local_thread_catalog)")}
        if not {"host_id", "thread_id"}.issubset(cat_cols):
            raise RuntimeError("local_thread_catalog schema changed")
        state_cols = {r[1] for r in state.execute("pragma table_info(threads)")}
        if not {"id", "archived", "archived_at", "rollout_path"}.issubset(state_cols):
            raise RuntimeError("threads schema changed")
        if automation_id:
            row = app.execute(
                "select name from automations where id=?", (automation_id,)
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Automation id not found: {automation_id}")
            if row[0] != title:
                raise RuntimeError(
                    f"Automation title mismatch for {automation_id!r}: expected {title!r}, found {row[0]!r}"
                )
    finally:
        app.close()
        state.close()


def snapshot_status(app_db: Path, state_db: Path, sessions: list[Session]) -> dict[str, dict]:
    app = connect_ro(app_db)
    state = connect_ro(state_db)
    try:
        out: dict[str, dict] = {}
        for s in sessions:
            t = state.execute(
                "select archived, archived_at, rollout_path from threads where id=?", (s.thread_id,)
            ).fetchone()
            a = app.execute(
                "select automation_id,status,read_at,archived_reason from automation_runs where thread_id=?",
                (s.thread_id,),
            ).fetchone()
            c = app.execute(
                "select count(*) from local_thread_catalog where host_id='local' and thread_id=?",
                (s.thread_id,),
            ).fetchone()[0]
            out[s.thread_id] = {
                "updated_at": s.updated_at,
                "thread": None if t is None else {
                    "archived": bool(t[0]),
                    "archived_at": t[1],
                    "rollout_path": t[2],
                },
                "automation_run": None if a is None else {
                    "automation_id": a[0],
                    "status": a[1],
                    "read_at": a[2],
                    "archived_reason": a[3],
                },
                "catalog_rows": c,
            }
        return out
    finally:
        app.close()
        state.close()


def backup_sqlite(src_path: Path) -> Path:
    stamp = int(time.time())
    dst_path = src_path.with_name(f"{src_path.name}.backup-scheduled-cleanup-{stamp}")
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dst_path


def run_archive(codex_bin: Path, thread_id: str) -> tuple[bool, str]:
    cp = subprocess.run(
        [str(codex_bin), "archive", thread_id],
        text=True,
        capture_output=True,
    )
    msg = (cp.stdout or cp.stderr or "").strip().replace("\n", " ")[:500]
    return cp.returncode == 0, msg


def apply_side_effects(app_db: Path, old_ids: list[str]) -> tuple[int, int]:
    if not old_ids:
        return (0, 0)
    q = ",".join("?" for _ in old_ids)
    now = int(time.time() * 1000)
    con = sqlite3.connect(app_db, timeout=15)
    try:
        with con:
            con.execute(
                f"UPDATE automation_runs SET status='ARCHIVED', updated_at=?, "
                f"archived_reason=COALESCE(archived_reason,'auto') WHERE thread_id IN ({q})",
                [now, *old_ids],
            )
            archived_runs = con.execute(
                f"SELECT count(*) FROM automation_runs WHERE thread_id IN ({q}) AND status='ARCHIVED'",
                old_ids,
            ).fetchone()[0]
            removed = con.execute(
                f"DELETE FROM local_thread_catalog WHERE host_id='local' AND thread_id IN ({q})",
                old_ids,
            ).rowcount
            if removed and table_exists(con, "local_thread_catalog_metadata"):
                con.execute(
                    "UPDATE local_thread_catalog_metadata "
                    "SET catalog_revision=catalog_revision+1 WHERE id=1"
                )
        return archived_runs, removed
    finally:
        con.close()


def emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"Matched sessions: {payload['matched_count']}")
    print(f"Keep newest: {payload['keep_count']}")
    for item in payload["keep"]:
        print(f"  KEEP    {item['thread_id']}  {item['updated_at']}")
    for item in payload["archive"]:
        print(f"  ARCHIVE {item['thread_id']}  {item['updated_at']}")
    if not payload["applied"]:
        print("Dry-run only. Re-run with --apply to make changes.")
    else:
        print(f"Backups: {', '.join(payload['backups'])}")
        print(
            f"Result: automation_runs_archived={payload['automation_runs_archived']} "
            f"catalog_rows_removed={payload['catalog_rows_removed']}"
        )


def main() -> int:
    args = parse_args()
    if args.keep < 1:
        raise RuntimeError("--keep must be at least 1")
    codex_home = args.codex_home.expanduser().resolve()
    index = codex_home / "session_index.jsonl"
    state_db = codex_home / "state_5.sqlite"
    app_db = find_app_db(codex_home)
    codex_bin = find_codex_bin(args.codex_bin)

    sessions = load_sessions(index, args.title)
    validate_schema(app_db, state_db, args.automation_id, args.title)
    before = snapshot_status(app_db, state_db, sessions)

    keep = sessions[: args.keep]
    old = sessions[args.keep :]
    payload = {
        "title": args.title,
        "automation_id": args.automation_id,
        "matched_count": len(sessions),
        "keep_count": min(args.keep, len(sessions)),
        "keep": [s.__dict__ for s in keep],
        "archive": [s.__dict__ for s in old],
        "applied": False,
        "backups": [],
        "automation_runs_archived": 0,
        "catalog_rows_removed": 0,
        "archive_command_results": [],
        "before": before,
    }

    if not args.apply or not old:
        emit(payload, args.json)
        return 0

    payload["backups"] = [str(backup_sqlite(app_db)), str(backup_sqlite(state_db))]

    for s in old:
        current = before.get(s.thread_id, {})
        thread_state = current.get("thread") or {}
        if thread_state.get("archived"):
            payload["archive_command_results"].append(
                {"thread_id": s.thread_id, "skipped": True, "reason": "already_archived"}
            )
            continue
        ok, msg = run_archive(codex_bin, s.thread_id)
        payload["archive_command_results"].append(
            {"thread_id": s.thread_id, "ok": ok, "message": msg}
        )
        if not ok:
            raise RuntimeError(f"Codex archive failed for {s.thread_id}: {msg}")

    archived_runs, removed = apply_side_effects(app_db, [s.thread_id for s in old])
    payload["automation_runs_archived"] = archived_runs
    payload["catalog_rows_removed"] = removed
    payload["after"] = snapshot_status(app_db, state_db, sessions)
    payload["applied"] = True

    for s in keep:
        after = payload["after"].get(s.thread_id, {})
        run = after.get("automation_run") or {}
        if run.get("status") == "ARCHIVED":
            raise RuntimeError(f"Safety check failed: kept session was archived: {s.thread_id}")
    for s in old:
        after = payload["after"].get(s.thread_id, {})
        run = after.get("automation_run") or {}
        if run and run.get("status") != "ARCHIVED":
            raise RuntimeError(f"Verification failed: automation run not archived: {s.thread_id}")
        if after.get("catalog_rows") not in (0, None):
            raise RuntimeError(f"Verification failed: stale catalog row remains: {s.thread_id}")

    emit(payload, args.json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
