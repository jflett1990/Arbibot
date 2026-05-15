from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class OutcomeSide(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass(frozen=True, slots=True)
class EdgeInput:
    outcome_side: OutcomeSide
    fair_up_probability: Decimal
    fair_down_probability: Decimal
    executable_price: Decimal
    target_size: Decimal
    fee_cost: Decimal = Decimal("0")
    slippage_cost: Decimal = Decimal("0")
    spread_cost: Decimal = Decimal("0")
    latency_risk: Decimal = Decimal("0")
    queue_uncertainty: Decimal = Decimal("0")
    model_error_buffer: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class EdgeResult:
    outcome_side: OutcomeSide
    fair_probability: Decimal
    executable_price: Decimal
    gross_edge: Decimal
    net_edge: Decimal
    target_size: Decimal
    fee_cost: Decimal
    slippage_cost: Decimal
    spread_cost: Decimal
    latency_risk: Decimal
    queue_uncertainty: Decimal
    model_error_buffer: Decimal
    is_positive: bool


def calculate_edge(input: EdgeInput) -> EdgeResult:
    for name, p in {
        "fair_up_probability": input.fair_up_probability,
        "fair_down_probability": input.fair_down_probability,
    }.items():
        if p < 0 or p > 1:
            raise ValueError(f"{name} must be within [0,1]")

    if input.executable_price <= 0 or input.executable_price >= 1:
        raise ValueError("executable_price must be > 0 and < 1")
    if input.target_size <= 0:
        raise ValueError("target_size must be > 0")

    costs = [
        input.fee_cost,
        input.slippage_cost,
        input.spread_cost,
        input.latency_risk,
        input.queue_uncertainty,
        input.model_error_buffer,
    ]
    if any(cost < 0 for cost in costs):
        raise ValueError("all costs/frictions must be >= 0")

    fair_probability = (
        input.fair_up_probability
        if input.outcome_side is OutcomeSide.UP
        else input.fair_down_probability
    )
    gross_edge = fair_probability - input.executable_price
    net_edge = gross_edge - sum(costs, Decimal("0"))

    return EdgeResult(
        outcome_side=input.outcome_side,
        fair_probability=fair_probability,
        executable_price=input.executable_price,
        gross_edge=gross_edge,
        net_edge=net_edge,
        target_size=input.target_size,
        fee_cost=input.fee_cost,
        slippage_cost=input.slippage_cost,
        spread_cost=input.spread_cost,
        latency_risk=input.latency_risk,
        queue_uncertainty=input.queue_uncertainty,
        model_error_buffer=input.model_error_buffer,
        is_positive=net_edge > 0,
    )
