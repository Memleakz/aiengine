import sqlite3
import json

db_path = "challenge_workspace/logs/agent_traces.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cursor = conn.execute("SELECT id, type, data FROM traces WHERE data LIKE '%server.py%'")
for row in cursor.fetchall():
    print(f"\n--- Trace #{row['id']} Type: {row['type']} ---")
    print(row['data'])
conn.close()
