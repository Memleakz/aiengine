import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# Dynamically find the directory containing 'agent_engine' and 'backend'
def add_paths():
    current = Path(__file__).resolve().parent
    
    # Add the parent of 'backend' so 'from backend...' works
    if str(current.parent) not in sys.path:
        sys.path.insert(0, str(current.parent))
        
    # Search for agent_engine up to 5 levels up
    search_ptr = current
    for _ in range(5):
        if (search_ptr / "agent_engine").exists():
            if str(search_ptr) not in sys.path:
                sys.path.insert(0, str(search_ptr))
            return True
        search_ptr = search_ptr.parent
    return False

if not add_paths():
    print("Warning: could not find agent_engine directory in parents")

engine_import_error = None
try:
    from backend.engine_bridge import engine_event_to_ws_event

    from agent_engine.engine import LightweightEngine
    from agent_engine.events import AgentEvent
except Exception as e:
    engine_import_error = str(e)
    print(f"CRITICAL: Could not import agent_engine components: {e}")
    import traceback
    traceback.print_exc()
    LightweightEngine = None
    AgentEvent = None
    engine_event_to_ws_event = None

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Agent Web CLI")

# CORS middleware to allow cross-origin requests from the frontend
# Note: If allow_credentials is True, allow_origins cannot be ["*"] in Starlette.
# We use allow_origin_regex as a workaround to allow all origins with credentials if requested.
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]

if "*" in allowed_origins:
    cors_kwargs = {"allow_origin_regex": ".*"}
else:
    cors_kwargs = {"allow_origins": allowed_origins}

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    **cors_kwargs
)

# Session middleware for simple authentication
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET", "default-insecure-secret"),
    session_cookie="ai_kanban_session",
    max_age=3600 * 24 * 7,  # 1 week
    same_site="lax",
    https_only=False  # Set to False for compatibility; change to True if using HTTPS only
)

class LoginRequest(BaseModel):
    password: str

def is_auth_enabled():
    return os.getenv("APP_ENV") == "production"

def check_auth(request: Request):
    if is_auth_enabled():
        if not request.session.get("authenticated", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
    return True

# Serve the frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# Concurrency limit: max 10 simultaneous WebSocket connections
MAX_CONNECTIONS = 10
connection_semaphore = asyncio.Semaphore(MAX_CONNECTIONS)
active_connections: set[WebSocket] = set()


@app.get("/")
async def serve_index() -> HTMLResponse:
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    return HTMLResponse(content="<h1>Frontend not built</h1>", status_code=404)


@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "engine_available": LightweightEngine is not None,
        "engine_error": engine_import_error
    }


@app.get("/api/auth/status")
async def auth_status(request: Request):
    enabled = is_auth_enabled()
    authenticated = request.session.get("authenticated", False) if enabled else True
    return {
        "enabled": enabled,
        "authenticated": authenticated
    }


@app.post("/api/auth/login")
async def login(request: Request, login_data: LoginRequest):
    if not is_auth_enabled():
        return {"status": "ok", "message": "Auth disabled"}
    
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": "ADMIN_PASSWORD not configured on server"}
        )
        
    if login_data.password == admin_password:
        request.session["authenticated"] = True
        return {"status": "ok"}
    
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"status": "error", "message": "Invalid password"}
    )


@app.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@app.websocket("/")
async def websocket_root_fallback(websocket: WebSocket):
    """
    Fallback for when the client tries to connect to the root instead of /ws.
    This helps avoid 403 Forbidden errors when the frontend URL calculation is off.
    """
    await websocket.accept()
    await websocket.send_text(
        json.dumps({
            "event": "error",
            "data": {"message": "WebSocket connection should be to /ws endpoint. Redirecting logic..."},
        })
    )
    await websocket.close(code=1000)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Check authentication if enabled
    if is_auth_enabled():
        if not websocket.session.get("authenticated", False):
            await websocket.accept()
            await websocket.send_text(
                json.dumps({
                    "event": "error",
                    "data": {"message": "Authentication required"},
                })
            )
            await websocket.close(code=1008, reason="Authentication required")
            return

    # Check concurrency limit before accepting
    if connection_semaphore.locked():
        await websocket.accept()
        await websocket.send_text(
            json.dumps({
                "event": "error",
                "data": {"message": "Server at capacity. Please try again later."},
            })
        )
        await websocket.close(code=1008, reason="Max connections reached")
        return

    await websocket.accept()

    if LightweightEngine is None:
        await websocket.send_text(
            json.dumps({
                "event": "error",
                "data": {"message": "AI engine not available. Check server logs."},
            })
        )
        await websocket.close()
        return

    # Acquire semaphore for connection limit
    await connection_semaphore.acquire()
    active_connections.add(websocket)
    engine = None

    try:
        # Determine workdir: use environment variable or default
        workdir = os.getenv("AGENT_WORKDIR")
        if not workdir:
            workdir = str(project_root)
        # print(f"[DEBUG] Backend starting with workdir: {workdir}")

        # Define tools to allow
        allowed_tools = [
            "bash", "read_file", "file_write", "file_edit", "glob_search", "grep_search",
            "web_fetch", "web_search", "python_repl", "sleep", "get_time",
            "manage_tasks", "subagent", "notebook_edit", "git_tool", "manage_todo",
            "cron_tool", "skill_tool", "code_analysis", "system_info", "network_tool",
            "get_tool_guide"
        ]

        engine = LightweightEngine(
            workdir=workdir,
            allowed_tools=allowed_tools,
            manage_history=True,
            system_prompt="You are a helpful AI coding assistant with access to tools to modify files and run commands. You are operating in the project root."
        )

        # Load MCP config (searches CWD, workdir, and package source)
        await engine.load_mcp_config("mcp_config.json")

        # Track active task so we don't block the websocket receive loop
        active_task = None
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("event") == "user_command":
                    command = message.get("data", {}).get("text", "")
                    # Input validation: max 10000 characters
                    if len(command) > 10000:
                        await websocket.send_text(
                            json.dumps({
                                "event": "validation_error",
                                "data": {"message": "Message too long (max 10000 characters)"},
                            })
                        )
                        continue
                    if command:
                        engine._cancel_flow = False
                        active_task = asyncio.create_task(_process_command(engine, websocket, command))
                elif message.get("event") == "run_flow":
                    flow_data = message.get("data", {})
                    if flow_data:
                        engine._cancel_flow = False
                        active_task = asyncio.create_task(_process_flow(engine, websocket, flow_data))
                elif message.get("event") == "stop":
                    engine._is_running = False
                    engine._cancel_flow = True
                elif message.get("event") == "update_settings":
                    try:
                        settings = message.get("data", {})
                        updated = []
                        if "workdir" in settings:
                            if is_auth_enabled():
                                print(f"[SECURITY] Blocked workdir change attempt in production mode")
                            else:
                                engine.set_workdir(settings["workdir"])
                                updated.append("workdir")
                        if "system_prompt" in settings:
                            engine.set_system_prompt(settings["system_prompt"])
                            updated.append("system_prompt")
                        if "parameters" in settings:
                            engine.update_completion_kwargs(**settings["parameters"])
                            updated.append("parameters")
                        
                        await websocket.send_text(json.dumps({
                            "event": "settings_updated",
                            "data": {"updated": updated}
                        }))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "event": "error",
                            "data": {"message": f"Failed to update settings: {str(e)}"}
                        }))
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({
                        "event": "error",
                        "data": {"message": "Invalid JSON format"},
                    })
                )
    except WebSocketDisconnect:
        print("Client disconnected")
    except asyncio.CancelledError:
        print("Websocket task was cancelled.")
    except Exception as e:
        print(f"Error: {e}")
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await websocket.send_text(
                json.dumps({
                    "event": "error",
                    "data": {"message": f"Server error: {str(e)}"},
                })
            )
    finally:
        # Stop any active processing task
        if active_task and not active_task.done():
            active_task.cancel()
            try:
                await active_task
            except asyncio.CancelledError:
                pass

        # Engine lifecycle: ensure cleanup on disconnect
        if engine is not None:
            try:
                engine._is_running = False
                await engine.close()
            except Exception as e:
                print(f"Error during engine cleanup: {e}")
        # Release semaphore and remove from active connections
        active_connections.discard(websocket)
        connection_semaphore.release()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await websocket.close()


async def _process_command(engine: LightweightEngine, websocket: WebSocket, command: str):
    """Process a command through the engine and forward events to the client."""
    try:
        async for agent_event in engine.run(command):
            ws_event = await engine_event_to_ws_event(agent_event)
            if ws_event is not None:
                await websocket.send_text(json.dumps(ws_event))
    except Exception as e:
        await websocket.send_text(
            json.dumps({
                "event": "error",
                "data": {"message": f"Engine error: {str(e)}"},
            })
        )

async def _process_flow(engine: LightweightEngine, websocket: WebSocket, flow_data: dict):
    """Orchestrate a sequence of agents passing accumulated context."""
    agents = flow_data.get("agents", [])
    initial_prompt = flow_data.get("initial_prompt", "")
    
    if not agents:
        await websocket.send_text(json.dumps({"event": "error", "data": {"message": "No agents provided in flow."}}))
        return

    await websocket.send_text(json.dumps({"event": "flow_start", "data": {"total_agents": len(agents)}}))
    
    global_context = f"# Initial Request\n\n{initial_prompt}\n\n"
    
    for idx, agent in enumerate(agents):
        agent_name = agent.get("name", f"Agent_{idx+1}")
        system_prompt = agent.get("system_prompt", "")
        
        await websocket.send_text(json.dumps({
            "event": "flow_step_start",
            "data": {"agent_name": agent_name, "step": idx+1, "total": len(agents)}
        }))
        
        # Reset engine history for a fresh context
        engine.history = []
        engine.set_system_prompt(system_prompt)
        
        execution_prompt = f"CONTEXT:\n{global_context}\n\nTASK: Execute your specific phase based on your system instructions. Do not ask for clarification, just execute."
        
        # Capture the final text output of this agent
        agent_output = ""
        
        try:
            async for agent_event in engine.run(execution_prompt):
                # Accumulate the final text
                if agent_event.type == "token":
                    agent_output += str(agent_event.data)
                
                ws_event = await engine_event_to_ws_event(agent_event)
                if ws_event is not None:
                    # Inject the agent_name into the event payload
                    ws_event["agent_name"] = agent_name
                    await websocket.send_text(json.dumps(ws_event))
        except Exception as e:
            await websocket.send_text(
                json.dumps({
                    "event": "error",
                    "data": {"message": f"Engine error in step {idx+1} ({agent_name}): {str(e)}"},
                    "agent_name": agent_name
                })
            )
            # Break the flow on error
            break
            
        if getattr(engine, "_cancel_flow", False):
            await websocket.send_text(json.dumps({"event": "error", "data": {"message": "Flow cancelled by user."}}))
            break
            
        # Accumulate the output into the global context
        global_context += f"## Phase: {agent_name}\n{agent_output}\n\n"
        
        # Write the persistent log
        try:
            log_path = Path(engine.workdir) / "flow_execution_log.md"
            log_path.write_text(global_context, encoding="utf-8")
        except Exception as e:
            print(f"Warning: Failed to write flow log: {e}")
            
        await websocket.send_text(json.dumps({
            "event": "flow_step_complete",
            "data": {"agent_name": agent_name}
        }))
        
    await websocket.send_text(json.dumps({"event": "flow_complete", "data": {"status": "success"}}))
