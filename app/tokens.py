import os
import sqlite3
import secrets
import datetime
from flask import g, current_app

# Path to SQLite DB (adjust if yours is different)
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "nvrwall.db",
)


def get_db():
    """
    Get a per-request SQLite connection with:
    - timeout to reduce 'database is locked'
    - row_factory=Row for dict-like access
    """
    if "db" not in g:
        g.db = sqlite3.connect(
            DB_PATH,
            timeout=10,              # wait up to 10s if locked
            check_same_thread=False, # allow use across threads (gunicorn workers)
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    """
    Call this from create_app() so teardown happens automatically.
    """
    app.teardown_appcontext(close_db)


def init_db():
    """
    Create tables if they do not exist.
    You can delete the old nvrwall.db once to reset to this schema.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            revoked INTEGER NOT NULL DEFAULT 0,
            last_used_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id INTEGER,
            path TEXT,
            ip TEXT,
            user_agent TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(token_id) REFERENCES tokens(id)
        )
        """
    )

    db.commit()
    db.close()


# ---- Token operations --------------------------------------------------------


def create_token(description: str, days_valid: int | None = None) -> str:
    """
    Create a new token.

    description: human-readable label
    days_valid: if provided, token expires after N days; otherwise no expiry
    """
    db = get_db()
    token = secrets.token_urlsafe(48)
    now = datetime.datetime.utcnow()
    expires_at = None
    if days_valid:
        expires_at = (now + datetime.timedelta(days=days_valid)).isoformat()

    db.execute(
        """
        INSERT INTO tokens (token, description, created_at, expires_at, revoked)
        VALUES (?, ?, ?, ?, 0)
        """,
        (token, description, now.isoformat(), expires_at),
    )
    db.commit()
    return token


def is_token_valid(token: str | None) -> int | None:
    """
    Return token_id if valid (exists, not revoked, not expired), else None.
    """
    if not token:
        return None

    db = get_db()
    row = db.execute(
        """
        SELECT id, revoked, expires_at
        FROM tokens
        WHERE token = ?
        """,
        (token,),
    ).fetchone()

    if row is None:
        return None

    if row["revoked"]:
        return None

    if row["expires_at"]:
        try:
            exp = datetime.datetime.fromisoformat(row["expires_at"])
            if datetime.datetime.utcnow() > exp:
                # considered expired
                return None
        except Exception:
            # bad date stored; treat as invalid
            return None

    return row["id"]


def revoke_token(token_id: int) -> None:
    """
    Mark token as revoked.
    """
    db = get_db()
    db.execute("UPDATE tokens SET revoked = 1 WHERE id = ?", (token_id,))
    db.commit()


def list_tokens():
    """
    Return all tokens with derived fields:
    - last_access_at from access_logs
    - is_expired flag
    """
    db = get_db()
    now_iso = datetime.datetime.utcnow().isoformat()
    rows = db.execute(
        """
        SELECT
            t.id,
            t.token,
            t.description,
            t.created_at,
            t.expires_at,
            t.revoked,
            t.last_used_at,
            (
              SELECT MAX(created_at)
              FROM access_logs al
              WHERE al.token_id = t.id
            ) AS last_access_at,
            CASE
              WHEN t.expires_at IS NOT NULL AND t.expires_at < ? THEN 1
              ELSE 0
            END AS is_expired
        FROM tokens t
        ORDER BY t.created_at DESC
        """,
        (now_iso,),
    ).fetchall()
    return rows


def log_access(token_id: int, path: str, ip: str | None, user_agent: str | None):
    """
    Log token usage and update last_used_at on the token.
    """
    db = get_db()
    now_iso = datetime.datetime.utcnow().isoformat()

    db.execute(
        """
        INSERT INTO access_logs (token_id, path, ip, user_agent, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (token_id, path, ip, user_agent, now_iso),
    )
    db.execute(
        "UPDATE tokens SET last_used_at = ? WHERE id = ?",
        (now_iso, token_id),
    )
    db.commit()
