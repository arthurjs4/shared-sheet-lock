"""Tiny CLI: sheet-lock <workbook> --owner NAME <command>."""
from __future__ import annotations

import argparse
import json
import sys

from .core import LockError, SharedSheet


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sheet-lock")
    p.add_argument("workbook")
    p.add_argument("--owner", required=True)
    p.add_argument("--lock-hours", type=float, default=4)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("acquire")
    sub.add_parser("release")
    for name in ("reserve", "unreserve"):
        sub.add_parser(name).add_argument("resource")
    add = sub.add_parser("add", help="add rows from a JSON list file")
    add.add_argument("json_file")
    add.add_argument("--require-lock", action="store_true")
    a = p.parse_args(argv)
    s = SharedSheet(a.workbook, a.owner, lock_hours=a.lock_hours)
    try:
        if a.cmd == "status":
            print(json.dumps({"round_lock": s.round_status(), "reservations": s.reservations()}, indent=2))
        elif a.cmd == "acquire":
            print("acquired until", s.acquire_round()["expires_at"])
        elif a.cmd == "release":
            s.release_round()
            print("released")
        elif a.cmd == "reserve":
            print("reserved until", s.reserve(a.resource)["expires_at"])
        elif a.cmd == "unreserve":
            s.release(a.resource)
            print("released", a.resource)
        elif a.cmd == "add":
            with open(a.json_file, encoding="utf-8") as fh:
                res = s.add_rows(json.load(fh), require_round_lock=a.require_lock)
            print(f"added {len(res.added)}, rejected {len(res.rejected)}")
            for _, why in res.rejected:
                print("  rejected:", why)
    except LockError as e:
        print("LOCKED:", e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
