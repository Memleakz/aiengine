import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    type: str  # "token" | "thinking" | "system" | "tool_start" | "tool_result" | "error" | "done"
    data: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
