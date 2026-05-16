from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class _RiskConfigLike(Protocol):
    @property
    def account_equity(self) -> Decimal: ...

    @property
    def risk_per_trade_pct(self) -> Decimal: ...

    @property
    def daily_loss_cap_pct(self) -> Decimal: ...

    @property
    def hard_stop_pct(self) -> Decimal: ...

    @property
    def max_market_exposure_pct(self) -> Decimal: ...

    @property
    def max_daily_traded_notional_pct(self) -> Decimal: ...


def max_loss_per_trade(config: _RiskConfigLike) -> Decimal:
    return config.account_equity * config.risk_per_trade_pct


def daily_loss_limit(config: _RiskConfigLike) -> Decimal:
    return config.account_equity * config.daily_loss_cap_pct


def hard_stop_limit(config: _RiskConfigLike) -> Decimal:
    return config.account_equity * config.hard_stop_pct


def max_market_exposure(config: _RiskConfigLike) -> Decimal:
    return config.account_equity * config.max_market_exposure_pct


def max_daily_traded_notional(config: _RiskConfigLike) -> Decimal:
    return config.account_equity * config.max_daily_traded_notional_pct


def suggest_buy_size_for_binary(
    config: _RiskConfigLike,
    price: Decimal,
    current_exposure: Decimal = Decimal("0"),
) -> Decimal:
    if price <= 0:
        raise ValueError("price must be > 0")

    risk_capacity = max_loss_per_trade(config)
    exposure_capacity = max_market_exposure(config) - current_exposure
    if risk_capacity <= 0 or exposure_capacity <= 0:
        return Decimal("0")

    size_by_risk = risk_capacity / price
    size_by_exposure = exposure_capacity / price
    return max(Decimal("0"), min(size_by_risk, size_by_exposure))
