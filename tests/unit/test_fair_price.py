import math
from decimal import Decimal

import pytest

from arbibot.core.events import FeatureSnapshot
from arbibot.model.fair_price import (
    FairPriceError,
    FairPriceInput,
    FairPriceModel,
    estimate_from_feature_snapshot,
)


def _input(
    spot: str,
    threshold: str,
    vol: str | None = "0.01",
    momentum: str | None = None,
    seconds_to_expiry: str = "60",
) -> FairPriceInput:
    return FairPriceInput(
        spot_price=Decimal(spot),
        threshold_price=Decimal(threshold),
        seconds_to_expiry=Decimal(seconds_to_expiry),
        realized_volatility=None if vol is None else Decimal(vol),
        momentum=None if momentum is None else Decimal(momentum),
    )


def test_basic_probability_behavior() -> None:
    m = FairPriceModel()
    above = m.estimate(_input("101", "100"))
    below = m.estimate(_input("99", "100"))
    equal = m.estimate(_input("100", "100", momentum="0"))
    assert above.fair_up_probability > Decimal("0.5")
    assert below.fair_up_probability < Decimal("0.5")
    assert abs(equal.fair_up_probability - Decimal("0.5")) < Decimal("0.01")
    assert above.fair_down_probability == Decimal("1") - above.fair_up_probability


def test_clamping_and_volatility_handling() -> None:
    m = FairPriceModel(min_volatility=Decimal("0.001"), max_volatility=Decimal("0.1"))
    res_none = m.estimate(_input("100", "100", vol=None))
    assert res_none.effective_volatility == Decimal("0.001")
    res_zero = m.estimate(_input("100", "100", vol="0"))
    assert res_zero.effective_volatility == Decimal("0.001")
    res_huge = m.estimate(_input("100", "100", vol="10"))
    assert res_huge.effective_volatility == Decimal("0.1")

    clamped = m.estimate(
        FairPriceInput(
            spot_price=Decimal("1000"),
            threshold_price=Decimal("1"),
            seconds_to_expiry=Decimal("1"),
            realized_volatility=Decimal("0.001"),
            min_probability=Decimal("0.1"),
            max_probability=Decimal("0.9"),
        )
    )
    assert clamped.fair_up_probability <= Decimal("0.9")
    assert clamped.fair_up_probability >= Decimal("0.1")


def test_momentum_and_shrinkage_effects() -> None:
    base = FairPriceModel(momentum_shrinkage=Decimal("0.1"))
    neutral = base.estimate(_input("100", "100", momentum="0"))
    pos = base.estimate(_input("100", "100", momentum="0.02", seconds_to_expiry="1"))
    neg = base.estimate(_input("100", "100", momentum="-0.02", seconds_to_expiry="1"))
    assert pos.fair_up_probability > neutral.fair_up_probability
    assert neg.fair_up_probability < neutral.fair_up_probability

    strong = FairPriceModel(momentum_shrinkage=Decimal("1"))
    pos_strong = strong.estimate(_input("100", "100", momentum="0.02", seconds_to_expiry="1"))
    assert pos_strong.fair_up_probability > pos.fair_up_probability


def test_time_validation_and_small_expiry() -> None:
    m = FairPriceModel()
    small = m.estimate(
        FairPriceInput(
            spot_price=Decimal("100"),
            threshold_price=Decimal("100"),
            seconds_to_expiry=Decimal("0.000001"),
            realized_volatility=Decimal("0.01"),
        )
    )
    assert not math.isnan(float(small.fair_up_probability))
    with pytest.raises(FairPriceError):
        m.estimate(
            FairPriceInput(
                spot_price=Decimal("100"),
                threshold_price=Decimal("100"),
                seconds_to_expiry=Decimal("0"),
                realized_volatility=Decimal("0.01"),
            )
        )


def test_validation_errors() -> None:
    with pytest.raises(FairPriceError):
        FairPriceModel(min_volatility=Decimal("0"))
    with pytest.raises(FairPriceError):
        FairPriceModel(max_volatility=Decimal("0"))
    with pytest.raises(FairPriceError):
        FairPriceModel(min_volatility=Decimal("1"), max_volatility=Decimal("0.1"))
    with pytest.raises(FairPriceError):
        FairPriceModel(momentum_shrinkage=Decimal("1.1"))

    m = FairPriceModel()
    with pytest.raises(FairPriceError):
        m.estimate(_input("0", "100"))
    with pytest.raises(FairPriceError):
        m.estimate(_input("100", "0"))
    with pytest.raises(FairPriceError):
        m.estimate(
            FairPriceInput(
                spot_price=Decimal("100"),
                threshold_price=Decimal("100"),
                seconds_to_expiry=Decimal("10"),
                realized_volatility=Decimal("0.01"),
                min_probability=Decimal("0.9"),
                max_probability=Decimal("0.8"),
            )
        )


def test_determinism_and_snapshot_helper() -> None:
    m = FairPriceModel()
    inp = _input("101", "100", vol="0.02", momentum="0.1")
    r1 = m.estimate(inp)
    r2 = m.estimate(inp)
    assert r1 == r2
    assert math.isfinite(float(r1.fair_up_probability))
    assert math.isfinite(float(r1.fair_down_probability))

    snap = FeatureSnapshot(
        event_id="f1",
        source="test",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        feature_set="x",
        values={},
        latest_price=100.0,
        realized_vol_30s=0.02,
        momentum_slope_5s=0.01,
    )
    out = estimate_from_feature_snapshot(snap, Decimal("101"), Decimal("60"))
    assert out.model_name.startswith("fair_price")

    bad = snap.model_copy(update={"latest_price": None})
    with pytest.raises(FairPriceError):
        estimate_from_feature_snapshot(bad, Decimal("101"), Decimal("60"))
