"""SharedSheet: expiring owner lock, resource reservation, duplicate barrier,
daily backup, atomic save. Rows are only ever appended, never deleted."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Sequence

from openpyxl import Workbook, load_workbook

from .normalize import normalize_domain, normalize_name, normalize_phone

DEFAULT_COLUMNS = ("Name", "Phone", "Website", "Status", "Added by", "Added at")
_FMT = "%Y-%m-%dT%H:%M:%S"


class LockError(RuntimeError):
    """Raised when a lock or reservation is held by someone else."""


@dataclass
class AddResult:
    added: list[dict] = field(default_factory=list)
    rejected: list[tuple[dict, str]] = field(default_factory=list)


class SharedSheet:
    def __init__(
        self,
        path: str | Path,
        owner: str,
        *,
        sheet: str = "Leads",
        columns: Sequence[str] = DEFAULT_COLUMNS,
        phone_column: str | None = "Phone",
        site_column: str | None = "Website",
        name_column: str | None = "Name",
        lock_hours: float = 4,
        reservation_hours: float = 6,
        backup_dir: str | Path | None = None,
        now: Callable[[], datetime] = datetime.now,
        mutex_timeout: float = 30,
    ) -> None:
        self.path = Path(path)
        self.owner = owner
        self.sheet = sheet
        self.columns = list(columns)
        self.phone_column, self.site_column, self.name_column = phone_column, site_column, name_column
        self.lock_hours, self.reservation_hours = lock_hours, reservation_hours
        self.backup_dir = Path(backup_dir) if backup_dir else self.path.parent / "backups"
        self.now = now
        self.mutex_timeout = mutex_timeout
        self._state_path = self.path.with_suffix(".state.json")
        self._mutex_path = self.path.with_suffix(".mutex")

    # ---- short mutex: protects every read-modify-write -------------------
    @contextmanager
    def _mutex(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.mutex_timeout
        while True:
            try:
                fd = os.open(self._mutex_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:  # a crashed process may have left it behind
                    if time.time() - self._mutex_path.stat().st_mtime > 60:
                        self._mutex_path.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise LockError("could not obtain the short write mutex")
                time.sleep(0.02)
            except PermissionError:  # Windows: file being deleted by the holder
                time.sleep(0.02)
        try:
            yield
        finally:
            try:
                self._mutex_path.unlink()
            except OSError:
                pass

    # ---- state file (round lock + reservations) --------------------------
    def _load_state(self) -> dict:
        if self._state_path.exists():
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        return {"round_lock": None, "reservations": {}}

    def _save_state(self, state: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self._state_path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, self._state_path)

    def _alive(self, entry: Mapping | None) -> bool:
        return bool(entry) and datetime.strptime(entry["expires_at"], _FMT) > self.now()

    def _entry(self, hours: float) -> dict:
        t = self.now()
        return {"owner": self.owner, "acquired_at": t.strftime(_FMT),
                "expires_at": (t + timedelta(hours=hours)).strftime(_FMT)}

    # ---- round lock -------------------------------------------------------
    def acquire_round(self) -> dict:
        """Take (or renew) the round lock. Expired locks are taken over."""
        with self._mutex():
            state = self._load_state()
            cur = state["round_lock"]
            if self._alive(cur) and cur["owner"] != self.owner:
                raise LockError(f"round locked by {cur['owner']} until {cur['expires_at']}")
            state["round_lock"] = self._entry(self.lock_hours)
            self._save_state(state)
            return state["round_lock"]

    def release_round(self) -> None:
        with self._mutex():
            state = self._load_state()
            cur = state["round_lock"]
            if self._alive(cur) and cur["owner"] != self.owner:
                raise LockError(f"round lock belongs to {cur['owner']}")
            state["round_lock"] = None
            self._save_state(state)

    def round_status(self) -> dict | None:
        cur = self._load_state()["round_lock"]
        return cur if self._alive(cur) else None

    # ---- resource reservation ---------------------------------------------
    def reserve(self, resource: str) -> dict:
        """Reserve one resource (e.g. a region or batch) so nobody else works on it."""
        with self._mutex():
            state = self._load_state()
            cur = state["reservations"].get(resource)
            if self._alive(cur) and cur["owner"] != self.owner:
                raise LockError(f"{resource!r} reserved by {cur['owner']} until {cur['expires_at']}")
            state["reservations"][resource] = self._entry(self.reservation_hours)
            self._save_state(state)
            return state["reservations"][resource]

    def release(self, resource: str) -> None:
        with self._mutex():
            state = self._load_state()
            cur = state["reservations"].get(resource)
            if self._alive(cur) and cur["owner"] != self.owner:
                raise LockError(f"{resource!r} reserved by {cur['owner']}")
            state["reservations"].pop(resource, None)
            self._save_state(state)

    def reservations(self) -> dict[str, dict]:
        return {k: v for k, v in self._load_state()["reservations"].items() if self._alive(v)}

    # ---- workbook ---------------------------------------------------------
    def _open(self):
        if self.path.exists():
            wb = load_workbook(self.path)
        else:
            wb = Workbook()
            wb.active.title = self.sheet
        if self.sheet not in wb.sheetnames:
            wb.create_sheet(self.sheet)
        ws = wb[self.sheet]
        if not ws._cells:  # brand-new empty sheet: write the header row
            ws.append(self.columns)
        return wb, ws

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        wb = load_workbook(self.path, read_only=True)
        data = list(wb[self.sheet].iter_rows(values_only=True))
        wb.close()
        if not data:
            return []
        head = data[0]
        return [dict(zip(head, r)) for r in data[1:] if any(v is not None for v in r)]

    def _keys(self, row: Mapping) -> dict[str, str]:
        k = {}
        if self.phone_column:
            k["phone"] = normalize_phone(row.get(self.phone_column))
        if self.site_column:
            k["site"] = normalize_domain(row.get(self.site_column))
        if self.name_column:
            k["name"] = normalize_name(row.get(self.name_column))
        return {a: b for a, b in k.items() if b}

    def backup_today(self) -> Path | None:
        """Copy the workbook once per day, before the first write of that day."""
        if not self.path.exists():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        dest = self.backup_dir / f"{self.path.stem}-{self.now():%Y-%m-%d}{self.path.suffix}"
        if not dest.exists():
            shutil.copy2(self.path, dest)
        return dest

    def add_rows(self, rows: Iterable[Mapping], *, require_round_lock: bool = False) -> AddResult:
        """Append rows that are not duplicates. Duplicates are reported, never overwritten."""
        result = AddResult()
        with self._mutex():
            if require_round_lock:
                cur = self._load_state()["round_lock"]
                if not (self._alive(cur) and cur["owner"] == self.owner):
                    raise LockError("you must hold the round lock to write")
            self.backup_today()
            wb, ws = self._open()
            head = [c.value for c in ws[1]]
            seen: dict[str, set[str]] = {"phone": set(), "site": set(), "name": set()}
            for r in ws.iter_rows(min_row=2, values_only=True):
                for kind, val in self._keys(dict(zip(head, r))).items():
                    seen[kind].add(val)
            stamp = self.now().strftime(_FMT)
            for raw in rows:
                row = dict(raw)
                row.setdefault("Added by", self.owner)
                row.setdefault("Added at", stamp)
                keys = self._keys(row)
                hit = next((k for k, v in keys.items() if v in seen[k]), None)
                if hit:
                    result.rejected.append((row, f"duplicate {hit}"))
                    continue
                ws.append([row.get(c) for c in head])
                for k, v in keys.items():
                    seen[k].add(v)
                result.added.append(row)
            if result.added:
                fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
                os.close(fd)
                wb.save(tmp)
                os.replace(tmp, self.path)
        return result
