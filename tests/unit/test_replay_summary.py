from arbibot.replay.summary import ReplaySummary


def test_replay_summary_defaults() -> None:
    s = ReplaySummary()
    assert s.total_events == 0
    assert s.order_events_total == 0
    assert s.net_pnl is None


def test_replay_summary_mutation() -> None:
    s = ReplaySummary()
    s.total_events += 1
    s.unknown_events += 1
    assert s.total_events == 1
    assert s.unknown_events == 1
