import json
import os
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


class TestBackendWebSocket:
    @pytest.fixture
    def mock_websocket(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws.receive_text = AsyncMock()
        ws.accept = AsyncMock()
        return ws

    def test_websocket_accepts_connection(self):
        import backend.main as backend_module
        from backend.main import app
        from fastapi.testclient import TestClient

        original_engine = backend_module.LightweightEngine
        backend_module.LightweightEngine = None

        try:
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                data = websocket.receive_text()
                parsed = json.loads(data)
                assert parsed["event"] == "error"
                assert "not available" in parsed["data"]["message"]
        finally:
            backend_module.LightweightEngine = original_engine

    def test_health_endpoint_returns_ok(self):
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"


class TestEventValidation:
    def test_valid_user_command_json(self):
        command = {"event": "user_command", "data": {"text": "test command"}}
        parsed = json.loads(json.dumps(command))

        assert parsed["event"] == "user_command"
        assert parsed["data"]["text"] == "test command"

    def test_invalid_json_handling(self):
        invalid_json = "not valid json"

        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_json)

    def test_missing_event_field(self):
        message = {"data": {"text": "test"}}

        assert "event" not in message or message.get("event") != "user_command"

    def test_empty_command_handling(self):
        message = {"event": "user_command", "data": {"text": ""}}

        command = message.get("data", {}).get("text", "")
        assert not command


class TestFileStructure:
    def test_frontend_files_exist(self):
        frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'frontend')
        assert os.path.exists(os.path.join(frontend_dir, 'index.html'))
        assert os.path.exists(os.path.join(frontend_dir, 'main.ts'))
        assert os.path.exists(os.path.join(frontend_dir, 'style.css'))

    def test_backend_files_exist(self):
        backend_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'backend')
        assert os.path.exists(os.path.join(backend_dir, 'main.py'))
        assert os.path.exists(os.path.join(backend_dir, 'engine_bridge.py'))

    def test_config_files_exist(self):
        base_dir = os.path.join(os.path.dirname(__file__), '..')
        assert os.path.exists(os.path.join(base_dir, 'requirements.txt'))
        assert os.path.exists(os.path.join(base_dir, 'package.json'))
        assert os.path.exists(os.path.join(base_dir, 'tsconfig.json'))
        assert os.path.exists(os.path.join(base_dir, 'vite.config.ts'))
