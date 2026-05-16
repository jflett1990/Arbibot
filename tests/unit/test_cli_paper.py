import json

from arbibot.apps.cli import main
from arbibot.storage.sqlite_store import SQLiteEventStore


def test_paper_missing_args(tmp_path) -> None:
    db = tmp_path / "events.sqlite3"
    SQLiteEventStore(db).close()
    rc = main(["paper", "--store", str(db)])
    assert rc == 1


def test_paper_json(tmp_path, capsys) -> None:
    db = tmp_path / "events.sqlite3"
    SQLiteEventStore(db).close()
    rc = main(
        [
            "paper",
            "--store",
            str(db),
            "--threshold-price",
            "100",
            "--seconds-to-expiry",
            "300",
            "--outcome-side",
            "UP",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "total_events" in payload
