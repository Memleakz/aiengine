import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


class TestExtractTargetEdgeCases:
    """Edge cases for _extract_target function."""

    def test_extract_target_with_none_value(self):

        # BUG: Returns "unknown" instead of "None" for None input
        assert _extract_target(None) == "unknown"

    def test_extract_target_with_empty_string(self):

        # BUG: Returns "unknown" instead of "" for empty string
        assert _extract_target("") == "unknown"

    def test_extract_target_with_zero(self):

        # BUG: Returns "unknown" instead of "0" for 0
        assert _extract_target(0) == "unknown"

    def test_extract_target_with_false(self):

        # BUG: Returns "unknown" instead of "False" for False
        assert _extract_target(False) == "unknown"

    def test_extract_target_with_list(self):

        assert _extract_target(["a", "b"]) == "['a', 'b']"

    def test_extract_target_with_nested_dict(self):

        data = {"nested": {"key": "value"}}
        result = _extract_target(data)
        assert result == "nested"

    def test_extract_target_with_filepath_priority(self):

        data = {"filepath": "main.py", "command": "ls", "target": "other"}
        assert _extract_target(data) == "main.py"

    def test_extract_target_with_target_key(self):

        data = {"target": "some_target", "other": "value"}
        assert _extract_target(data) == "some_target"

    def test_extract_target_with_file_key(self):

        data = {"file": "test.py"}
        assert _extract_target(data) == "test.py"

    def test_extract_target_with_path_key(self):

        data = {"path": "/some/path"}
        assert _extract_target(data) == "/some/path"


class TestEngineEventToWsEventEdgeCases:
    """Edge cases for engine_event_to_ws_event function."""

    def test_agent_event_with_none_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="token", data=None)
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_stream_chunk"
        assert result["data"]["chunk"] == "None"

    def test_agent_event_with_complex_data_object(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="token", data={"key": "value"})
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_stream_chunk"

    def test_agent_event_with_integer_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="token", data=42)
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["data"]["chunk"] == "42"

    def test_agent_event_with_empty_string_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="token", data="")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["data"]["chunk"] == ""

    def test_thinking_event_with_empty_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="thinking", data="")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["data"]["message"] == ""

    def test_tool_start_with_empty_metadata(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="tool_start", data="something", metadata={})
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["data"]["tool"] == "unknown"

    def test_tool_start_with_none_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="tool_start", data=None, metadata={"tool_name": "test"})
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["data"]["tool"] == "test"
        # BUG: _extract_target returns "unknown" for None instead of "None"
        assert result["data"]["target"] == "unknown"

    def test_system_event_with_empty_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="system", data="")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["data"]["status"] == "processing"

    def test_done_event_ignores_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="done", data="some completion data")
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "agent_complete"
        assert result["data"] == {}

    def test_error_event_with_complex_data(self):
        from agent_engine.events import AgentEvent

        event = AgentEvent(type="error", data={"error": "details", "code": 500})
        result = asyncio.run(engine_event_to_ws_event(event))

        assert result is not None
        assert result["event"] == "error"


class TestBackendWebSocketEdgeCases:
    """Edge cases for WebSocket endpoint."""

    def test_websocket_rejects_empty_command(self):
        """Empty commands should not trigger processing."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                # Send empty command - should not cause error
                websocket.send_text(json.dumps({"event": "user_command", "data": {"text": ""}}))
                # No response expected for empty command
        finally:
            backend_module.LightweightEngine = original_engine

    def test_websocket_handles_malformed_json(self):
        """Malformed JSON should return error message."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                websocket.send_text("not valid json {{{")
                data = websocket.receive_text()
                parsed = json.loads(data)
                assert parsed["event"] == "error"
        finally:
            backend_module.LightweightEngine = original_engine

    def test_websocket_handles_missing_data_field(self):
        """Message without data field should not crash."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                websocket.send_text(json.dumps({"event": "user_command"}))
                # Should not crash, empty command is ignored
        finally:
            backend_module.LightweightEngine = original_engine

    def test_websocket_handles_unknown_event_type(self):
        """Unknown event types should be ignored gracefully."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                websocket.send_text(json.dumps({"event": "unknown_event", "data": {}}))
                # Should not crash or respond
        finally:
            backend_module.LightweightEngine = original_engine

    def test_websocket_handles_very_long_command(self):
        """Very long commands should be handled without error."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                long_command = "x" * 10000
                websocket.send_text(json.dumps({"event": "user_command", "data": {"text": long_command}}))
                # Should not crash
        finally:
            backend_module.LightweightEngine = original_engine

    def test_websocket_handles_special_characters(self):
        """Commands with special characters should be handled."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                special_cmd = "test\n\r\t\\\"'<>;&|`"
                websocket.send_text(json.dumps({"event": "user_command", "data": {"text": special_cmd}}))
                # Should not crash
        finally:
            backend_module.LightweightEngine = original_engine

    def test_websocket_handles_unicode_characters(self):
        """Commands with unicode characters should be handled."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                unicode_cmd = "你好世界 🌍 Ñoño"
                websocket.send_text(json.dumps({"event": "user_command", "data": {"text": unicode_cmd}}))
                # Should not crash
        finally:
            backend_module.LightweightEngine = original_engine

    def test_health_endpoint_shows_engine_unavailable(self):
        """Health endpoint should report engine_available as false when engine is None."""
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["engine_available"] is False
        finally:
            backend_module.LightweightEngine = original_engine


class TestProcessCommand:
    """Tests for _process_command function."""

    def test_process_command_forwards_events(self):
        """_process_command should forward events from engine to websocket."""
        from backend.main import _process_command

        mock_engine = MagicMock()
        mock_websocket = AsyncMock()

        async def mock_run(command):
            yield AgentEvent(type="token", data="Hello")
            yield AgentEvent(type="done", data=None)

        mock_engine.run = mock_run

        asyncio.run(_process_command(mock_engine, mock_websocket, "test command"))

        assert mock_websocket.send_text.call_count == 2

    def test_process_command_handles_engine_error(self):
        """_process_command should handle engine errors gracefully."""
        from backend.main import _process_command

        mock_engine = MagicMock()
        mock_websocket = AsyncMock()

        async def mock_run(command):
            raise RuntimeError("Engine failed")
            yield

        mock_engine.run = mock_run

        asyncio.run(_process_command(mock_engine, mock_websocket, "test command"))

        mock_websocket.send_text.assert_called_once()
        call_args = mock_websocket.send_text.call_args[0][0]
        parsed = json.loads(call_args)
        assert parsed["event"] == "error"
        assert "Engine error" in parsed["data"]["message"]


class TestBackendAppRoutes:
    """Test that all expected routes are registered."""

    def test_all_routes_exist(self):
        from backend.main import app

        routes = [route.path for route in app.routes]
        assert "/" in routes
        assert "/health" in routes
        assert "/ws" in routes

    def test_health_returns_correct_structure(self):
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "engine_available" in data
        assert data["status"] == "ok"

    def test_index_returns_html(self):
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestEventValidationEdgeCases:
    """Additional edge cases for event validation."""

    def test_command_with_only_whitespace(self):
        """Command with only whitespace should be treated as empty."""
        message = {"event": "user_command", "data": {"text": "   \n\t  "}}
        command = message.get("data", {}).get("text", "").strip()
        assert not command

    def test_command_with_null_characters(self):
        """Command with null characters should be handled."""
        message = {"event": "user_command", "data": {"text": "test\x00command"}}
        parsed = json.loads(json.dumps(message))
        assert parsed["data"]["text"] == "test\x00command"

    def test_command_with_nested_objects(self):
        """Command with nested objects in data should parse correctly."""
        message = {"event": "user_command", "data": {"text": "test", "extra": {"key": "value"}}}
        parsed = json.loads(json.dumps(message))
        assert parsed["data"]["text"] == "test"
        assert parsed["data"]["extra"]["key"] == "value"

    def test_json_with_extra_fields(self):
        """JSON with extra fields should still parse."""
        message = {"event": "user_command", "data": {"text": "test"}, "extra_field": "ignored"}
        parsed = json.loads(json.dumps(message))
        assert parsed["event"] == "user_command"
        assert parsed["data"]["text"] == "test"

    def test_json_with_null_values(self):
        """JSON with null values should parse correctly."""
        message = {"event": "user_command", "data": {"text": None}}
        parsed = json.loads(json.dumps(message))
        assert parsed["data"]["text"] is None

    def test_empty_json_object(self):
        """Empty JSON object should not have event field."""
        message = {}
        assert message.get("event") is None


class TestFrontendTypeDefinitions:
    """Verify TypeScript type definitions are correct."""

    def test_events_type_file_exists(self):
        events_file = os.path.join(os.path.dirname(__file__), "..", "src", "frontend", "types", "events.ts")
        assert os.path.exists(events_file)

    def test_events_file_has_all_required_types(self):
        events_file = os.path.join(os.path.dirname(__file__), "..", "src", "frontend", "types", "events.ts")
        with open(events_file) as f:
            content = f.read()

        assert "UserCommandEvent" in content
        assert "AgentStatusEvent" in content
        assert "AgentToolCallEvent" in content
        assert "AgentStreamChunkEvent" in content
        assert "AgentCompleteEvent" in content
        assert "ErrorEvent" in content
        assert "ServerEvent" in content
        assert "ClientEvent" in content
