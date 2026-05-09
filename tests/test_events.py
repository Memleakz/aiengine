import time

from agent_engine.events import AgentEvent


def test_agent_event_required_fields():
    evt = AgentEvent(type="token", data="hello")
    assert evt.type == "token"
    assert evt.data == "hello"


def test_agent_event_default_metadata():
    evt = AgentEvent(type="system", data="msg")
    assert evt.metadata == {}


def test_agent_event_default_timestamp_is_recent():
    before = time.time()
    evt = AgentEvent(type="done", data="complete")
    after = time.time()
    assert before <= evt.timestamp <= after


def test_agent_event_custom_metadata():
    meta = {"tool_name": "bash", "call_id": "abc"}
    evt = AgentEvent(type="tool_start", data={"command": "ls"}, metadata=meta)
    assert evt.metadata["tool_name"] == "bash"


def test_agent_event_all_valid_types():
    for t in ("token", "system", "tool_start", "tool_result", "error", "done"):
        evt = AgentEvent(type=t, data=None)
        assert evt.type == t
