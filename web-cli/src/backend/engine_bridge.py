
from agent_engine.events import AgentEvent


async def engine_event_to_ws_event(agent_event: AgentEvent) -> dict | None:
    """Convert a single AgentEvent to a WebSocket JSON message dict.

    Returns None for events that should not be forwarded to the client
    (e.g., tool_result).
    """
    event_type = agent_event.type
    data = agent_event.data
    metadata = agent_event.metadata

    if event_type == "token":
        return {
            "event": "agent_stream_chunk",
            "data": {"chunk": str(data)},
        }

    elif event_type == "thinking":
        return {
            "event": "agent_thinking",
            "data": {"chunk": str(data)},
        }

    elif event_type == "tool_start":
        tool_name = metadata.get("tool_name", "unknown")
        target = _extract_target(data)
        return {
            "event": "agent_tool_call",
            "data": {
                "tool": tool_name,
                "target": target,
            },
        }

    elif event_type == "tool_result":
        return {
            "event": "agent_tool_done",
            "data": {
                "tool": metadata.get("tool_name", "unknown"),
                "output": str(data),
                "truncated": metadata.get("truncated", False),
            },
        }

    elif event_type == "system":
        return {
            "event": "agent_status",
            "data": {
                "status": "processing",
                "message": str(data),
            },
        }

    elif event_type == "done":
        return {
            "event": "agent_complete",
            "data": {
                "usage": metadata.get("usage"),
                "session_usage": metadata.get("session_usage")
            },
        }

    elif event_type == "error":
        return {
            "event": "error",
            "data": {"message": str(data)},
        }

    return None


def _extract_target(data: any) -> str:
    """Extract a human-readable target from tool call data."""
    import json
    if isinstance(data, dict):
        # If it's a simple command or path, we can return it as a string for the preview
        # but the UI will handle the full JSON if it's long.
        # However, for debugging "writing data", we want the full structure.
        return json.dumps(data, indent=2)
    return str(data) if data else "unknown"
