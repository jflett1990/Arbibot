from __future__ import annotations

from enum import StrEnum


class OrderType(StrEnum):
    FAK = "FAK"
    FOK = "FOK"
    LIMIT = "LIMIT"


class ExecutionSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
