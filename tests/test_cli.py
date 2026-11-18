import json

from shared_sheet_lock.cli import main


def test_cli_flow(tmp_path, capsys):
    wb = str(tmp_path / "w.xlsx")
    assert main([wb, "--owner", "alice", "acquire"]) == 0
    assert main([wb, "--owner", "bob", "acquire"]) == 2
    f = tmp_path / "rows.json"
    f.write_text(json.dumps([{"Name": "Sample Co", "Phone": "555-010-0100"}]))
    assert main([wb, "--owner", "alice", "add", str(f), "--require-lock"]) == 0
    assert "added 1" in capsys.readouterr().out
    assert main([wb, "--owner", "alice", "add", str(f)]) == 0
    assert "rejected 1" in capsys.readouterr().out
    assert main([wb, "--owner", "bob", "reserve", "batch-1"]) == 0
    assert main([wb, "--owner", "alice", "reserve", "batch-1"]) == 2
