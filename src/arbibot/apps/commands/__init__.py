from arbibot.apps.commands.paper import run_paper
from arbibot.apps.commands.record_binance import run_record_binance
from arbibot.apps.commands.replay import run_replay
from arbibot.apps.commands.status import run_status
from arbibot.apps.commands.validate_config import run_validate_config

__all__ = [
    "run_paper",
    "run_record_binance",
    "run_replay",
    "run_status",
    "run_validate_config",
]

from arbibot.apps.commands.research import run_research_critique, run_research_init, run_research_inspect, run_research_list, run_research_run
