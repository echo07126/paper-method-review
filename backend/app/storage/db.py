import sqlite3
from pathlib import Path

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        name TEXT NOT NULL,
        ir_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        report_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        state TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str) -> None:
    connection = connect(db_path)
    try:
        current = 0
        try:
            row = connection.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0 if row else 0
        except sqlite3.OperationalError:
            current = 0
        for index, script in enumerate(MIGRATIONS, start=1):
            if index <= current:
                continue
            connection.executescript(script)
            connection.execute("INSERT INTO schema_version (version) VALUES (?)", (index,))
            connection.commit()
    finally:
        connection.close()
