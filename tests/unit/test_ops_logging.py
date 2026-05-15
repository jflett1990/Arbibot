import io
import json

from arbibot.ops.logging import LogLevel, StructuredLogger


def test_logger_writes_json_and_preserves_fields() -> None:
    sink = io.StringIO()
    logger = StructuredLogger(sink=sink)
    logger.info(
        event="evt",
        message="hello",
        component="comp",
        correlation_id="cid1",
        metadata={"a": 1},
    )
    line = sink.getvalue().strip()
    payload = json.loads(line)
    assert payload["event"] == "evt"
    assert payload["message"] == "hello"
    assert payload["component"] == "comp"
    assert payload["correlation_id"] == "cid1"
    assert payload["metadata"] == {"a": 1}


def test_log_levels_and_multiple_lines() -> None:
    sink = io.StringIO()
    logger = StructuredLogger(sink=sink)
    logger.debug("e1", "m1", "c1")
    logger.warning("e2", "m2", "c2")
    logger.error("e3", "m3", "c3")
    logger.critical("e4", "m4", "c4")
    levels = [json.loads(line)["level"] for line in sink.getvalue().strip().splitlines()]
    assert levels == [
        LogLevel.DEBUG.value,
        LogLevel.WARNING.value,
        LogLevel.ERROR.value,
        LogLevel.CRITICAL.value,
    ]
