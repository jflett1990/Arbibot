from decimal import Decimal

from arbibot.core.events import FeatureSnapshot, PolyBookSnapshot
from arbibot.market.book import LocalOrderBook
from arbibot.model.fair_price import FairPriceResult
from arbibot.opportunity.detector import OpportunityDetector
from arbibot.opportunity.edge import OutcomeSide


def _fair(up: str = "0.65", down: str = "0.35") -> FairPriceResult:
    return FairPriceResult(
        fair_up_probability=Decimal(up),
        fair_down_probability=Decimal(down),
        z_score=Decimal("0"),
        effective_volatility=Decimal("0.01"),
        effective_momentum=Decimal("0"),
        seconds_to_expiry=Decimal("60"),
        model_name="m",
    )


def _snap(stale_spot: bool = False, stale_book: bool = False) -> FeatureSnapshot:
    return FeatureSnapshot(
        event_id="f",
        source="s",
        source_ts_ms=1000,
        recv_wall_ts_ms=1001,
        recv_monotonic_ns=1002,
        feature_set="x",
        values={},
        symbol="BTCUSDT",
        stale_spot=stale_spot,
        stale_book=stale_book,
    )


def _book(depth: float = 10, spread: tuple[float, float] = (0.5, 0.51)) -> LocalOrderBook:
    b = LocalOrderBook("tok")
    b.apply_snapshot(
        PolyBookSnapshot(
            event_id="s",
            source="p",
            source_ts_ms=1000,
            recv_wall_ts_ms=1001,
            recv_monotonic_ns=1002,
            market_id="m",
            outcome="UP",
            token_id="tok",
            bids=[[spread[0] - 0.01, depth]],
            asks=[[spread[1], depth], [spread[1] + 0.01, depth]],
        )
    )
    return b


def test_detector_behaviors() -> None:
    d = OpportunityDetector()
    dec = d.detect(_fair(), _book(), _snap(), Decimal("1"), OutcomeSide.UP, Decimal("60"))
    assert dec.gate_result.should_trade

    low = d.detect(_fair(), _book(depth=0.2), _snap(), Decimal("1"), OutcomeSide.UP, Decimal("60"))
    assert not low.gate_result.should_trade

    stale = d.detect(
        _fair(), _book(), _snap(stale_spot=True), Decimal("1"), OutcomeSide.UP, Decimal("60")
    )
    assert not stale.gate_result.should_trade

    down = d.detect(
        _fair("0.3", "0.7"), _book(), _snap(), Decimal("1"), OutcomeSide.DOWN, Decimal("60")
    )
    assert down.edge_result is not None and down.edge_result.fair_probability == Decimal("0.7")

    c1 = d.detect(
        _fair(),
        _book(),
        _snap(),
        Decimal("1"),
        OutcomeSide.UP,
        Decimal("60"),
        fee_cost=Decimal("0.05"),
    )
    c2 = d.detect(
        _fair(),
        _book(),
        _snap(),
        Decimal("1"),
        OutcomeSide.UP,
        Decimal("60"),
        fee_cost=Decimal("0.05"),
    )
    assert c1.gate_result.reasons == c2.gate_result.reasons
