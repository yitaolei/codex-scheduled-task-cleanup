#!/usr/bin/env python3
"""Install a macOS LaunchAgent that runs the cleanup script at selected local times."""

from __future__ import annotations

import argparse
import plistlib
import subprocess
from pathlib import Path


def parse_time(value: str) -> tuple[int, int]:
    try:
        h, m = map(int, value.split(":"))
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Invalid HH:MM time: {value}") from exc
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise argparse.ArgumentTypeError(f"Invalid HH:MM time: {value}")
    return h, m


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cleanup-script", type=Path, required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--automation-id")
    p.add_argument("--times", required=True, help="Comma-separated local times, e.g. 06:10,11:10,16:10")
    p.add_argument("--label", default="local.codex.scheduled-task-cleanup")
    args = p.parse_args()

    times = [parse_time(x.strip()) for x in args.times.split(",") if x.strip()]
    if not times:
        raise SystemExit("No valid times supplied")

    home = Path.home()
    plist = home / "Library" / "LaunchAgents" / f"{args.label}.plist"
    logs = home / "Library" / "Logs"
    logs.mkdir(parents=True, exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)

    program_args = [
        "/usr/bin/env",
        "python3",
        str(args.cleanup_script.expanduser().resolve()),
        "--title",
        args.title,
        "--apply",
    ]
    if args.automation_id:
        program_args += ["--automation-id", args.automation_id]

    payload = {
        "Label": args.label,
        "ProgramArguments": program_args,
        "StartCalendarInterval": [{"Hour": h, "Minute": m} for h, m in times],
        "RunAtLoad": False,
        "StandardOutPath": str(logs / f"{args.label}.log"),
        "StandardErrorPath": str(logs / f"{args.label}-error.log"),
    }
    with plist.open("wb") as f:
        plistlib.dump(payload, f, sort_keys=False)

    uid = subprocess.check_output(["id", "-u"], text=True).strip()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{args.label}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], check=True)
    print(f"Installed {args.label}: {plist}")
    for h, m in times:
        print(f"  {h:02d}:{m:02d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
