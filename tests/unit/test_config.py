from pathlib import Path

import pytest

from arbibot.core.config import load_config
from arbibot.core.errors import ConfigError


@pytest.mark.parametrize(
    "path",
    [
        Path("configs/default.yaml"),
        Path("configs/paper.yaml"),
        Path("configs/live_disabled.yaml"),
    ],
)
def test_configs_load(path: Path) -> None:
    config = load_config(path)
    assert config.mode in {"paper", "live"}


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ConfigError):
        load_config(missing)


@pytest.mark.parametrize(
    "path",
    [
        Path("configs/default.yaml"),
        Path("configs/paper.yaml"),
        Path("configs/live_disabled.yaml"),
    ],
)
def test_live_trading_disabled_in_repo_configs(path: Path) -> None:
    config = load_config(path)
    assert config.live_trading_enabled is False
