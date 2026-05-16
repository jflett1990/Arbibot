from decimal import Decimal

import pytest

from arbibot.risk.engine import RiskConfig
from arbibot.risk.limits import (
    daily_loss_limit,
    hard_stop_limit,
    max_daily_traded_notional,
    max_loss_per_trade,
    max_market_exposure,
    suggest_buy_size_for_binary,
)


def test_limit_calculations() -> None:
    cfg = RiskConfig(account_equity=Decimal("1000"))
    assert max_loss_per_trade(cfg) == Decimal("5")
    assert daily_loss_limit(cfg) == Decimal("20")
    assert hard_stop_limit(cfg) == Decimal("4")
    assert max_market_exposure(cfg) == Decimal("20")
    assert max_daily_traded_notional(cfg) == Decimal("200")


def test_suggested_size_respects_risk_per_trade() -> None:
    cfg = RiskConfig(account_equity=Decimal("1000"))
    assert suggest_buy_size_for_binary(cfg, Decimal("0.5")) == Decimal("10")


def test_suggested_size_respects_remaining_exposure() -> None:
    cfg = RiskConfig(account_equity=Decimal("1000"))
    assert suggest_buy_size_for_binary(cfg, Decimal("0.5"), Decimal("18")) == Decimal("4")


def test_suggested_size_zero_when_no_capacity() -> None:
    cfg = RiskConfig(account_equity=Decimal("1000"))
    assert suggest_buy_size_for_binary(cfg, Decimal("0.5"), Decimal("25")) == Decimal("0")


def test_invalid_price_raises() -> None:
    cfg = RiskConfig(account_equity=Decimal("1000"))
    with pytest.raises(ValueError):
        suggest_buy_size_for_binary(cfg, Decimal("0"))
