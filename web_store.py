"""SQLite persistence for Chat BTH projects, conversations and messages."""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("HERMES_DB_PATH", DATA_DIR / "chat_bth.db"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT 'auto',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                model TEXT,
                used_web INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
            """
        )


def as_dict(row):
    return dict(row) if row else None


def list_projects() -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT p.*, COUNT(c.id) AS conversation_count "
            "FROM projects p LEFT JOIN conversations c ON c.project_id=p.id "
            "GROUP BY p.id ORDER BY p.updated_at DESC"
        ).fetchall()
    return [as_dict(row) for row in rows]


def search_workspace(query: str, limit: int = 80) -> dict[str, list[dict]]:
    """Find projects and conversations without loading every chat into the browser."""
    value = query.strip()
    if not value:
        return {"projects": [], "conversations": []}
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    with connect() as db:
        projects = db.execute(
            "SELECT p.*, COUNT(c.id) AS conversation_count "
            "FROM projects p LEFT JOIN conversations c ON c.project_id=p.id "
            "WHERE p.name LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "GROUP BY p.id ORDER BY p.updated_at DESC LIMIT ?",
            (pattern, limit),
        ).fetchall()
        conversations = db.execute(
            "SELECT c.*, p.name AS project_name, COUNT(m.id) AS message_count "
            "FROM conversations c JOIN projects p ON p.id=c.project_id "
            "LEFT JOIN messages m ON m.conversation_id=c.id "
            "WHERE c.title LIKE ? ESCAPE '\\' COLLATE NOCASE "
            "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?",
            (pattern, limit),
        ).fetchall()
    return {
        "projects": [as_dict(row) for row in projects],
        "conversations": [as_dict(row) for row in conversations],
    }


def create_project(name: str) -> dict:
    project_id = uuid.uuid4().hex
    timestamp = now()
    with connect() as db:
        db.execute(
            "INSERT INTO projects(id, name, created_at, updated_at) VALUES(?, ?, ?, ?)",
            (project_id, name.strip()[:120] or "โปรเจกต์ใหม่", timestamp, timestamp),
        )
    return get_project(project_id)


def get_project(project_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return as_dict(row)


def update_project(project_id: str, name: str) -> dict | None:
    project = get_project(project_id)
    if not project:
        return None
    with connect() as db:
        db.execute("UPDATE projects SET name=?, updated_at=? WHERE id=?", (name.strip()[:120] or "โปรเจกต์ใหม่", now(), project_id))
    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    with connect() as db:
        cursor = db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    return cursor.rowcount > 0


def list_conversations(project_id: str) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT c.*, COUNT(m.id) AS message_count "
            "FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id "
            "WHERE c.project_id=? GROUP BY c.id ORDER BY c.updated_at DESC",
            (project_id,),
        ).fetchall()
    return [as_dict(row) for row in rows]


def create_conversation(project_id: str, title: str = "แชทใหม่", model: str = "auto") -> dict | None:
    if not get_project(project_id):
        return None
    conversation_id = uuid.uuid4().hex
    timestamp = now()
    with connect() as db:
        db.execute(
            "INSERT INTO conversations(id, project_id, title, model, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
            (conversation_id, project_id, title.strip()[:160] or "แชทใหม่", model, timestamp, timestamp),
        )
        db.execute("UPDATE projects SET updated_at=? WHERE id=?", (timestamp, project_id))
    return get_conversation(conversation_id)


def get_conversation(conversation_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
    return as_dict(row)


def update_conversation(conversation_id: str, title: str | None = None, model: str | None = None) -> dict | None:
    conversation = get_conversation(conversation_id)
    if not conversation:
        return None
    new_title = title.strip()[:160] if title is not None else conversation["title"]
    new_model = model if model is not None else conversation["model"]
    with connect() as db:
        db.execute(
            "UPDATE conversations SET title=?, model=?, updated_at=? WHERE id=?",
            (new_title or "แชทใหม่", new_model, now(), conversation_id),
        )
    return get_conversation(conversation_id)


def delete_conversation(conversation_id: str) -> bool:
    with connect() as db:
        cursor = db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    return cursor.rowcount > 0


def list_messages(conversation_id: str, limit: int = 48) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM (SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
            (conversation_id, limit),
        ).fetchall()
    return [as_dict(row) for row in rows]


def add_message(conversation_id: str, role: str, content: str, model: str | None = None, used_web: bool = False) -> dict:
    timestamp = now()
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO messages(conversation_id, role, content, model, used_web, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, model, int(used_web), timestamp),
        )
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (timestamp, conversation_id))
        row = db.execute("SELECT * FROM messages WHERE id=?", (cursor.lastrowid,)).fetchone()
    return as_dict(row)


def ensure_default_project() -> dict:
    projects = list_projects()
    return projects[0] if projects else create_project("สนทนาทั่วไป")


init_db()
