"""Deterministic proxy fair-probability model for BTC UP/DOWN markets.

Assumption: `seconds_to_expiry` and realized volatility are used in a local, seconds-based
scale (non-annualized) for monotonic proxy behavior, not options calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import erf, isfinite, log, sqrt

from arbibot.core.events import FeatureSnapshot


class FairPriceError(ValueError):
    """Raised when fair-price model inputs or configuration are invalid."""


@dataclass(frozen=True, slots=True)
class FairPriceInput:
    spot_price: Decimal
    threshold_price: Decimal
    seconds_to_expiry: Decimal
    realized_volatility: Decimal | None
    momentum: Decimal | None = None
    min_probability: Decimal = Decimal("0.001")
    max_probability: Decimal = Decimal("0.999")


@dataclass(frozen=True, slots=True)
class FairPriceResult:
    fair_up_probability: Decimal
    fair_down_probability: Decimal
    z_score: Decimal | None
    effective_volatility: Decimal
    effective_momentum: Decimal
    seconds_to_expiry: Decimal
    model_name: str


class FairPriceModel:
    def __init__(
        self,
        min_volatility: Decimal = Decimal("0.0001"),
        max_volatility: Decimal = Decimal("0.25"),
        momentum_shrinkage: Decimal = Decimal("0.10"),
    ) -> None:
        if min_volatility <= 0 or max_volatility <= 0:
            raise FairPriceError("volatility bounds must be > 0")
        if min_volatility > max_volatility:
            raise FairPriceError("min_volatility must be <= max_volatility")
        if momentum_shrinkage < 0 or momentum_shrinkage > 1:
            raise FairPriceError("momentum_shrinkage must be between 0 and 1")
        self.min_volatility = min_volatility
        self.max_volatility = max_volatility
        self.momentum_shrinkage = momentum_shrinkage

    def estimate(self, input: FairPriceInput) -> FairPriceResult:
        self._validate_input(input)

        tau = float(input.seconds_to_expiry)
        effective_vol = self._effective_volatility(input.realized_volatility)
        effective_momentum = (input.momentum or Decimal("0")) * self.momentum_shrinkage

        s = float(input.spot_price)
        k = float(input.threshold_price)
        mu = float(effective_momentum)
        sigma = float(effective_vol)

        variance = max((sigma * sigma) * tau, 1e-18)
        std = sqrt(variance)
        mean = log(s / k) + (mu * tau)
        z = mean / std

        up_prob = Decimal(str(self._normal_cdf(z)))
        up_prob = self._clamp_probability(up_prob, input.min_probability, input.max_probability)
        down_prob = Decimal("1") - up_prob

        if not (isfinite(float(up_prob)) and isfinite(float(down_prob))):
            raise FairPriceError("non-finite probability output")

        return FairPriceResult(
            fair_up_probability=up_prob,
            fair_down_probability=down_prob,
            z_score=Decimal(str(z)),
            effective_volatility=effective_vol,
            effective_momentum=effective_momentum,
            seconds_to_expiry=input.seconds_to_expiry,
            model_name="fair_price_lognormal_proxy_v1",
        )

    @staticmethod
    def _normal_cdf(x: float) -> float:
        return 0.5 * (1.0 + erf(x / sqrt(2.0)))

    def _effective_volatility(self, realized_volatility: Decimal | None) -> Decimal:
        if realized_volatility is None or realized_volatility <= 0:
            return self.min_volatility
        if realized_volatility < self.min_volatility:
            return self.min_volatility
        if realized_volatility > self.max_volatility:
            return self.max_volatility
        return realized_volatility

    @staticmethod
    def _clamp_probability(value: Decimal, min_p: Decimal, max_p: Decimal) -> Decimal:
        if value < min_p:
            return min_p
        if value > max_p:
            return max_p
        return value

    @staticmethod
    def _validate_input(input: FairPriceInput) -> None:
        if input.spot_price <= 0:
            raise FairPriceError("spot_price must be > 0")
        if input.threshold_price <= 0:
            raise FairPriceError("threshold_price must be > 0")
        if input.seconds_to_expiry <= 0:
            raise FairPriceError("seconds_to_expiry must be > 0")
        if input.min_probability <= 0:
            raise FairPriceError("min_probability must be > 0")
        if input.max_probability >= 1:
            raise FairPriceError("max_probability must be < 1")
        if input.min_probability >= input.max_probability:
            raise FairPriceError("min_probability must be < max_probability")


def estimate_from_feature_snapshot(
    snapshot: FeatureSnapshot,
    threshold_price: Decimal,
    seconds_to_expiry: Decimal,
    model: FairPriceModel | None = None,
) -> FairPriceResult:
    if snapshot.latest_price is None:
        raise FairPriceError("FeatureSnapshot.latest_price is required")

    volatility = snapshot.realized_vol_30s
    if volatility is None:
        volatility = snapshot.realized_vol_5s
    momentum = snapshot.momentum_slope_5s
    if momentum is None:
        momentum = snapshot.return_5s

    estimator = model or FairPriceModel()
    return estimator.estimate(
        FairPriceInput(
            spot_price=Decimal(str(snapshot.latest_price)),
            threshold_price=threshold_price,
            seconds_to_expiry=seconds_to_expiry,
            realized_volatility=None if volatility is None else Decimal(str(volatility)),
            momentum=None if momentum is None else Decimal(str(momentum)),
        )
    )
