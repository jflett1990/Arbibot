from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import TextIO

from arbibot.core.time import now_wall_ms


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class LogRecord:
    timestamp_ms: int
    level: LogLevel
    event: str
    message: str
    component: str
    correlation_id: str | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


class StructuredLogger:
    def __init__(self, sink: TextIO | None = None) -> None:
        self._sink: TextIO = sink or sys.stdout

    def log(
        self,
        level: LogLevel,
        event: str,
        message: str,
        component: str,
        correlation_id: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> LogRecord:
        record = LogRecord(
            timestamp_ms=now_wall_ms(),
            level=level,
            event=event,
            message=message,
            component=component,
            correlation_id=correlation_id,
            metadata=metadata,
        )
        payload = asdict(record)
        payload["level"] = level.value
        self._sink.write(f"{json.dumps(payload, sort_keys=True)}\n")
        return record

    def debug(
        self,
        event: str,
        message: str,
        component: str,
        correlation_id: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> LogRecord:
        return self.log(
            LogLevel.DEBUG,
            event,
            message,
            component,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def info(
        self,
        event: str,
        message: str,
        component: str,
        correlation_id: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> LogRecord:
        return self.log(
            LogLevel.INFO,
            event,
            message,
            component,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def warning(
        self,
        event: str,
        message: str,
        component: str,
        correlation_id: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> LogRecord:
        return self.log(
            LogLevel.WARNING,
            event,
            message,
            component,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def error(
        self,
        event: str,
        message: str,
        component: str,
        correlation_id: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> LogRecord:
        return self.log(
            LogLevel.ERROR,
            event,
            message,
            component,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def critical(
        self,
        event: str,
        message: str,
        component: str,
        correlation_id: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> LogRecord:
        return self.log(
            LogLevel.CRITICAL,
            event,
            message,
            component,
            correlation_id=correlation_id,
            metadata=metadata,
        )
