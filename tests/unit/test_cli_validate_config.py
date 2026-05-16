import json

from arbibot.apps.cli import main


def test_validate_config_ok_and_json(capsys) -> None:
    rc = main(["validate-config", "--config", "configs/default.yaml", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["ok"] is True


def test_validate_config_missing_nonzero(capsys) -> None:
    rc = main(["validate-config", "--config", "configs/missing.yaml"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "invalid" in out.lower()
