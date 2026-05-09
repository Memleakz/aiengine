import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Add src root for agent_engine
SRC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Add web-cli src for backend
WEB_CLI_SRC = Path(__file__).resolve().parent.parent / "src"
if str(WEB_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(WEB_CLI_SRC))

from backend.engine_bridge import _extract_target, engine_event_to_ws_event  # noqa: E402

from agent_engine.events import AgentEvent  # noqa: E402


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestEngineBridge:
    def test_token_event_translates_to_stream_chunk(self):

        event = AgentEvent(type="token", data="Hello world")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_stream_chunk"
        assert result["data"]["chunk"] == "Hello world"

    def test_thinking_event_translates_to_status(self):

        event = AgentEvent(type="thinking", data="Analyzing code...")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_status"
        assert result["data"]["status"] == "thinking"
        assert result["data"]["message"] == "Analyzing code..."

    def test_tool_start_event_translates_to_tool_call(self):

        event = AgentEvent(
            type="tool_start",
            data={"filepath": "auth.py"},
            metadata={"tool_name": "read_file"},
        )
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_tool_call"
        assert result["data"]["tool"] == "read_file"
        assert result["data"]["target"] == "auth.py"

    def test_tool_result_event_returns_none(self):

        event = AgentEvent(type="tool_result", data="result content")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is None

    def test_system_event_translates_to_processing_status(self):

        event = AgentEvent(type="system", data="Requesting completion...")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_status"
        assert result["data"]["status"] == "processing"
        assert result["data"]["message"] == "Requesting completion..."

    def test_done_event_translates_to_complete(self):

        event = AgentEvent(type="done", data="Run complete")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_complete"
        assert result["data"] == {}

    def test_error_event_translates_to_error(self):

        event = AgentEvent(type="error", data="Something went wrong")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "error"
        assert result["data"]["message"] == "Something went wrong"

    def test_unknown_event_returns_none(self):

        event = AgentEvent(type="unknown_type", data="test")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is None

    def test_extract_target_from_dict_with_filepath(self):

        data = {"filepath": "main.py", "content": "..."}
        assert _extract_target(data) == "main.py"

    def test_extract_target_from_dict_with_command(self):

        data = {"command": "ls -la"}
        assert _extract_target(data) == "ls -la"

    def test_extract_target_from_string(self):

        assert _extract_target("some string") == "some string"

    def test_extract_target_from_empty_dict(self):

        assert _extract_target({}) == "unknown"


class TestBackendApp:
    def test_health_endpoint(self):
        from backend.main import app

        assert "/health" in [route.path for route in app.routes]

    def test_index_endpoint(self):
        from backend.main import app

        assert "/" in [route.path for route in app.routes]

    def test_websocket_endpoint(self):
        from backend.main import app

        assert "/ws" in [route.path for route in app.routes]
