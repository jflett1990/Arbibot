import json

from arbibot.apps.cli import main
from arbibot.apps.commands.status import run_status


def test_status_json_parseable(capsys) -> None:
    rc = main(["status", "--config", "configs/default.yaml", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "health" in payload
    assert "metrics" in payload


def test_status_deterministic_generated_at(capsys) -> None:
    rc = run_status("configs/default.yaml", as_json=True, generated_at_ms=123)
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["generated_at_ms"] == 123
