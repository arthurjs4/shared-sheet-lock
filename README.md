# shared-sheet-lock

Let two people, agents or machines work on **one `.xlsx` file** without trampling each other.

Spreadsheets are a great shared "database" for a small team, until two writers save at the same time and one of them silently loses rows. `shared-sheet-lock` adds the minimum safety net around an `openpyxl` workbook:

| Feature | What it does |
| --- | --- |
| **Expiring round lock** | One owner at a time, default **4 hours**. The lock records who holds it and when it expires; an expired lock can be taken over, so a crashed session never blocks the team forever. |
| **Resource reservation** | Reserve one named resource (a region, a batch, a queue...) so two workers never process the same one. Reservations expire too (default 6 h). |
| **Duplicate barrier** | Before appending, each row is compared with the existing ones by normalised **phone** (last 10 digits), **website domain** and **name** (lower-case, accent-free, alphanumerics only). Duplicates are reported, never written. |
| **Daily backup** | The first write of each day copies the workbook to `backups/<name>-YYYY-MM-DD.xlsx` *before* touching it. |
| **Append-only** | The API has no delete. Rows are never removed or overwritten. |
| **Safe concurrent writes** | Every read-modify-write runs under a short file mutex and the workbook is saved atomically (temp file + `os.replace`). |

## Install

```bash
pip install -e ".[test]"
```

## Library usage

```python
from shared_sheet_lock import SharedSheet, LockError

sheet = SharedSheet("data/leads.xlsx", owner="agent-a")   # lock_hours=4 by default

sheet.acquire_round()                 # raises LockError if someone else holds it
sheet.reserve("region-7")             # one resource at a time
result = sheet.add_rows([
    {"Name": "Sample Cafe", "Phone": "+1 555-010-0001", "Website": "https://sample.example.com"},
])
print(len(result.added), "added;", [why for _, why in result.rejected])
sheet.release("region-7")
sheet.release_round()
```

Column names, the sheet name, which columns feed the duplicate check, lock durations and the backup folder are all constructor arguments.

## CLI

```bash
sheet-lock data/leads.xlsx --owner agent-a acquire
sheet-lock data/leads.xlsx --owner agent-a reserve region-7
sheet-lock data/leads.xlsx --owner agent-a add rows.json --require-lock
sheet-lock data/leads.xlsx --owner agent-b status
sheet-lock data/leads.xlsx --owner agent-a release
```

Exit code `2` means "locked by someone else".

## How it works

State (round lock + reservations) lives in a small JSON file next to the workbook (`leads.state.json`). All changes go through a short `O_EXCL` file mutex (`leads.mutex`, auto-recovered if stale after 60 s), so two processes can never interleave a read-modify-write.

The test suite starts two real OS processes that append 25 rows each at the same time and asserts all 50 rows are present afterwards.

## Limits

- Designed for two (or a few) writers on a **local or synced folder**. File locking over flaky network drives or cloud-sync clients is best effort.
- Not a database. If you need many writers, use one.

## Tests

```bash
pytest
```

## License

MIT
