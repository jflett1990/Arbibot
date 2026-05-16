import json

from arbibot.apps.cli import main
from arbibot.storage.sqlite_store import SQLiteEventStore


def test_replay_empty_store_json(tmp_path, capsys) -> None:
    db = tmp_path / "events.sqlite3"
    store = SQLiteEventStore(db)
    store.close()
    rc = main(["replay", "--store", str(db), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["total_events"] == 0


def test_replay_validation_errors(tmp_path, capsys) -> None:
    db = tmp_path / "events.sqlite3"
    SQLiteEventStore(db).close()
    rc = main(["replay", "--store", str(db), "--evaluate-opportunities"])
    assert rc == 1

    rc2 = main(["replay", "--store", str(db), "--paper-execute"])
    assert rc2 == 1
