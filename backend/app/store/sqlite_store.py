import json
import sqlite3
from datetime import datetime, timezone

from .base import Store


class SQLiteStore(Store):
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.executescript(
                """CREATE TABLE IF NOT EXISTS docs (kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                   updated_at TEXT, PRIMARY KEY (kind, id));"""
            )

    def list(self, kind):
        with self.lock:
            rows = self.db.execute("SELECT data FROM docs WHERE kind=? ORDER BY rowid", (kind,)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def get(self, kind, id):
        with self.lock:
            r = self.db.execute("SELECT data FROM docs WHERE kind=? AND id=?", (kind, id)).fetchone()
        return json.loads(r["data"]) if r else None

    def put(self, kind, id, data):
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO docs(kind,id,data,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (kind, id, json.dumps(data), now))

    def delete(self, kind, id):
        with self.lock, self.db:
            self.db.execute("DELETE FROM docs WHERE kind=? AND id=?", (kind, id))
