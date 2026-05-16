from arbibot.live.runtime import LivePilotRuntimeState


def test_runtime_state_behaviors() -> None:
    s = LivePilotRuntimeState(session_id="s1", started_at_ms=1)
    assert s.can_submit_more(1)
    s.mark_order_submitted("cid", "d1")
    assert s.orders_submitted == 1
    assert s.last_client_order_id == "cid"
    assert s.last_decision_event_id == "d1"
    assert not s.can_submit_more(1)

    s.disable("A")
    s.disable("A")
    assert s.disabled
    assert s.disable_reasons == ["A"]

    s.reset_session("s2", 2)
    assert s.session_id == "s2"
    assert s.orders_submitted == 0
    assert not s.disabled
    assert s.disable_reasons == []
