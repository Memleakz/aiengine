import sqlite3
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

class TraceLogger:
    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _init_db(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS traces (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        timestamp TEXT,
                        type TEXT,
                        data TEXT,
                        metadata TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON traces(session_id)")
        except Exception as e:
            print(f"TraceLogger Init Error: {e}")

    def log_event(self, session_id: str, event_type: str, data: Any, metadata: Optional[Dict] = None):
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.execute(
                    "INSERT INTO traces (session_id, timestamp, type, data, metadata) VALUES (?, ?, ?, ?, ?)",
                    (
                        session_id,
                        datetime.now().isoformat(),
                        event_type,
                        json.dumps(data) if not isinstance(data, str) else data,
                        json.dumps(metadata or {})
                    )
                )
        except Exception as e:
            # We don't want logging failures to crash the agent
            print(f"Logging Error: {e}")

    def get_session_history(self, session_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM traces WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
