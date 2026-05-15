"""Vendor-neutral ingestion contracts and deterministic mocks."""

from arbibot.ingestion.binance_ws import (
    BinanceClientConfig,
    BinancePayloadError,
    BinanceSpotMarketDataClient,
    parse_binance_payload,
)
from arbibot.ingestion.interfaces import (
    EventStreamClient,
    ExternalSignalClient,
    PredictionMarketDataClient,
    SpotMarketDataClient,
    persist_stream,
)
from arbibot.ingestion.mock_clients import (
    MockExternalSignalClient,
    MockPredictionMarketDataClient,
    MockSpotMarketDataClient,
)

__all__ = [
    "BinanceClientConfig",
    "BinancePayloadError",
    "BinanceSpotMarketDataClient",
    "EventStreamClient",
    "ExternalSignalClient",
    "MockExternalSignalClient",
    "MockPredictionMarketDataClient",
    "MockSpotMarketDataClient",
    "PredictionMarketDataClient",
    "SpotMarketDataClient",
    "parse_binance_payload",
    "persist_stream",
]
