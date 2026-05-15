from decimal import Decimal

from arbibot.risk.engine import KILL_SWITCH_ACTIVE, RiskConfig, RiskEngine
from arbibot.risk.kill_switch import KillSwitch


def test_kill_switch_defaults_activate_deactivate() -> None:
    ks = KillSwitch()
    assert ks.active is False
    assert ks.reason is None
    ks.activate("manual")
    assert ks.active is True
    assert ks.reason == "manual"
    ks.deactivate()
    assert ks.active is False
    assert ks.reason is None


def test_kill_switch_blocks_risk_engine() -> None:
    engine = RiskEngine(RiskConfig(account_equity=Decimal("1000")))
    engine.activate_kill_switch("panic")
    result = engine.check_new_order(Decimal("0.5"), Decimal("1"))
    assert result.allowed is False
    assert KILL_SWITCH_ACTIVE in result.reasons
