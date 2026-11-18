import multiprocessing as mp
from datetime import datetime, timedelta

import pytest

from shared_sheet_lock import LockError, SharedSheet, normalize_domain, normalize_name, normalize_phone


def test_normalizers():
    assert normalize_phone("+1 (555) 010-0001") == "5550100001"
    assert normalize_phone("123") == ""
    assert normalize_domain("https://www.Example.com/a?b") == "example.com"
    assert normalize_name("Café  São-Paulo!") == "cafesaopaulo"


def test_lock_blocks_other_owner_and_expires(tmp_path):
    clock = [datetime(2030, 1, 1, 8)]

    def mk(who):
        return SharedSheet(tmp_path / "w.xlsx", who, now=lambda: clock[0])

    a, b = mk("alice"), mk("bob")
    a.acquire_round()
    with pytest.raises(LockError):
        b.acquire_round()
    a.acquire_round()  # owner can renew
    clock[0] += timedelta(hours=4, minutes=1)
    assert b.round_status() is None
    b.acquire_round()  # takeover after expiry
    with pytest.raises(LockError):
        a.release_round()


def test_reservation_one_at_a_time(tmp_path):
    a = SharedSheet(tmp_path / "w.xlsx", "alice")
    b = SharedSheet(tmp_path / "w.xlsx", "bob")
    a.reserve("region-1")
    with pytest.raises(LockError):
        b.reserve("region-1")
    b.reserve("region-2")
    a.release("region-1")
    b.reserve("region-1")


def test_duplicate_barrier(tmp_path):
    s = SharedSheet(tmp_path / "w.xlsx", "alice")
    s.add_rows([{"Name": "Acme Café", "Phone": "555-010-0001", "Website": "https://acme.example.com"}])
    res = s.add_rows([
        {"Name": "Other", "Phone": "+1 555 010 0001"},                      # phone
        {"Name": "Different", "Website": "http://www.acme.example.com/x"},  # site
        {"Name": "ACME CAFE"},                                              # name, no accent
        {"Name": "Fresh", "Phone": "555-010-0002"},
    ])
    assert [r[1] for r in res.rejected] == ["duplicate phone", "duplicate site", "duplicate name"]
    assert len(res.added) == 1 and len(s.rows()) == 2


def test_duplicates_inside_one_batch(tmp_path):
    s = SharedSheet(tmp_path / "w.xlsx", "a")
    res = s.add_rows([{"Name": "X One", "Phone": "555-010-0009"}, {"Name": "X Two", "Phone": "555-010-0009"}])
    assert len(res.added) == 1 and len(res.rejected) == 1


def test_daily_backup_made_once_and_before_write(tmp_path):
    s = SharedSheet(tmp_path / "w.xlsx", "a", now=lambda: datetime(2030, 5, 1, 9))
    s.add_rows([{"Name": "One", "Phone": "555-010-0001"}])
    s.add_rows([{"Name": "Two", "Phone": "555-010-0002"}])  # same day: no new backup
    s.add_rows([{"Name": "Three", "Phone": "555-010-0003"}])
    backup = tmp_path / "backups" / "w-2030-05-01.xlsx"
    assert backup.exists()
    assert len(SharedSheet(backup, "x").rows()) == 1  # snapshot taken before the day's 2nd write


def test_never_deletes_rows(tmp_path):
    s = SharedSheet(tmp_path / "w.xlsx", "a")
    s.add_rows([{"Name": f"Item {c}", "Phone": f"555-010-00{i:02d}"} for i, c in enumerate("abc")])
    s.add_rows([{"Name": "Item a"}])  # rejected, existing untouched
    assert len(s.rows()) == 3
    assert not hasattr(s, "delete_row")


def test_require_round_lock(tmp_path):
    s = SharedSheet(tmp_path / "w.xlsx", "a")
    with pytest.raises(LockError):
        s.add_rows([{"Name": "N"}], require_round_lock=True)
    s.acquire_round()
    assert len(s.add_rows([{"Name": "N"}], require_round_lock=True).added) == 1


def _writer(path, who, n):
    s = SharedSheet(path, who)
    for i in range(n):
        s.add_rows([{"Name": f"{who} item {i}", "Phone": f"555-{ord(who[0]):03d}-{i:04d}"}])


def test_two_concurrent_writers_lose_nothing(tmp_path):
    path = str(tmp_path / "w.xlsx")
    n = 25
    procs = [mp.Process(target=_writer, args=(path, who, n)) for who in ("alice", "bob")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(180)
    assert all(p.exitcode == 0 for p in procs)
    names = {r["Name"] for r in SharedSheet(path, "x").rows()}
    assert names == {f"{w} item {i}" for w in ("alice", "bob") for i in range(n)}
