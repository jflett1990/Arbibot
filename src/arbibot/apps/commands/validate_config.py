from __future__ import annotations

import json
from pathlib import Path

from arbibot.core.config import load_config


def run_validate_config(config_path: str, as_json: bool) -> int:
    path = Path(config_path)
    try:
        load_config(path)
    except Exception as exc:  # noqa: BLE001
        if as_json:
            print(json.dumps({"ok": False, "config_path": str(path), "error": str(exc)}))
        else:
            print(f"Config invalid: {path}\nError: {exc}")
        return 1

    if as_json:
        print(json.dumps({"ok": True, "config_path": str(path)}))
    else:
        print(f"Config valid: {path}")
    return 0
