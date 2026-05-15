"""Core Arbibot exception types."""


class ArbibotError(Exception):
    """Base exception for Arbibot errors."""


class ConfigError(ArbibotError):
    """Raised when configuration loading or validation fails."""


class EventValidationError(ArbibotError):
    """Raised when event validation fails outside model parsing."""


class StaleDataError(ArbibotError):
    """Raised when required market data is stale."""


class LiveTradingDisabledError(ArbibotError):
    """Raised when live-trading operations are attempted while disabled."""


class UnknownOrderStateError(ArbibotError):
    """Raised when an order enters or reports an unknown state."""


class RiskLimitExceededError(ArbibotError):
    """Raised when a risk limit veto is triggered."""
