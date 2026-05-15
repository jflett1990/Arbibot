from decimal import Decimal

import pytest

from arbibot.opportunity.edge import EdgeInput, OutcomeSide, calculate_edge


def test_edge_calculation_up_down_and_costs() -> None:
    up = calculate_edge(
        EdgeInput(
            outcome_side=OutcomeSide.UP,
            fair_up_probability=Decimal("0.6"),
            fair_down_probability=Decimal("0.4"),
            executable_price=Decimal("0.5"),
            target_size=Decimal("10"),
        )
    )
    assert up.fair_probability == Decimal("0.6")
    assert up.gross_edge == Decimal("0.1")
    assert up.is_positive

    down = calculate_edge(
        EdgeInput(
            outcome_side=OutcomeSide.DOWN,
            fair_up_probability=Decimal("0.6"),
            fair_down_probability=Decimal("0.4"),
            executable_price=Decimal("0.3"),
            target_size=Decimal("10"),
            fee_cost=Decimal("0.01"),
            slippage_cost=Decimal("0.01"),
            spread_cost=Decimal("0.01"),
            latency_risk=Decimal("0.01"),
            queue_uncertainty=Decimal("0.01"),
            model_error_buffer=Decimal("0.2"),
        )
    )
    assert down.fair_probability == Decimal("0.4")
    assert down.net_edge < 0
    assert not down.is_positive


def test_edge_validation() -> None:
    with pytest.raises(ValueError):
        calculate_edge(
            EdgeInput(
                outcome_side=OutcomeSide.UP,
                fair_up_probability=Decimal("1.1"),
                fair_down_probability=Decimal("0"),
                executable_price=Decimal("0.5"),
                target_size=Decimal("1"),
            )
        )
    with pytest.raises(ValueError):
        calculate_edge(
            EdgeInput(
                outcome_side=OutcomeSide.UP,
                fair_up_probability=Decimal("0.5"),
                fair_down_probability=Decimal("0.5"),
                executable_price=Decimal("1"),
                target_size=Decimal("1"),
            )
        )
    with pytest.raises(ValueError):
        calculate_edge(
            EdgeInput(
                outcome_side=OutcomeSide.UP,
                fair_up_probability=Decimal("0.5"),
                fair_down_probability=Decimal("0.5"),
                executable_price=Decimal("0.5"),
                target_size=Decimal("0"),
            )
        )
