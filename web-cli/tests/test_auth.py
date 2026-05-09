import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import patch
from pathlib import Path
import sys

# Add the web-cli src directory to sys.path
web_cli_src = Path(__file__).resolve().parent.parent / "src"
if str(web_cli_src) not in sys.path:
    sys.path.insert(0, str(web_cli_src))

# Add the project root for agent_engine imports
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Mock .env loading before importing main
with patch("backend.main.load_dotenv"):
    from backend.main import app

def test_auth_status_disabled():
    with patch.dict(os.environ, {"APP_ENV": "development"}):
        client = TestClient(app)
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["authenticated"] is True

def test_auth_status_enabled_not_authenticated():
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        client = TestClient(app)
        # We need a new client/session for each test to be clean
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["authenticated"] is False

def test_login_success():
    with patch.dict(os.environ, {
        "APP_ENV": "production",
        "ADMIN_PASSWORD": "super-secret-password",
        "SESSION_SECRET": "test-secret"
    }):
        client = TestClient(app)
        # Try login
        response = client.post("/api/auth/login", json={"password": "super-secret-password"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        # Check status again - should be authenticated
        response = client.get("/api/auth/status")
        assert response.json()["authenticated"] is True

def test_login_failure():
    with patch.dict(os.environ, {
        "APP_ENV": "production",
        "ADMIN_PASSWORD": "super-secret-password"
    }):
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"password": "wrong-password"})
        assert response.status_code == 401
        assert response.json()["status"] == "error"

def test_logout():
    with patch.dict(os.environ, {
        "APP_ENV": "production",
        "ADMIN_PASSWORD": "super-secret-password"
    }):
        client = TestClient(app)
        # Login
        client.post("/api/auth/login", json={"password": "super-secret-password"})
        assert client.get("/api/auth/status").json()["authenticated"] is True
        
        # Logout
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        
        # Check status - should be unauthenticated
        assert client.get("/api/auth/status").json()["authenticated"] is False
