import secrets
from .database import get_db

# Generate a secure random token (URL-safe)
def generate_token():
    return secrets.token_urlsafe(48)   # very long, very secure


def create_token(description):
    token = generate_token()
    db = get_db()
    db.execute(
        "INSERT INTO tokens (token, description) VALUES (?, ?)",
        (token, description),
    )
    db.commit()
    return token


def revoke_token(token):
    db = get_db()
    db.execute(
        "UPDATE tokens SET revoked = 1 WHERE token = ?",
        (token,)
    )
    db.commit()


def is_token_valid(token):
    db = get_db()
    row = db.execute(
        "SELECT id, revoked FROM tokens WHERE token = ?",
        (token,)
    ).fetchone()

    if row is None:
        return None   # no such token

    if row["revoked"] == 1:
        return None   # revoked

    return row["id"]   # valid → return token_id


def log_access(token_id, path, ip, user_agent):
    db = get_db()
    db.execute(
        "INSERT INTO access_log (token_id, path, ip, user_agent) VALUES (?, ?, ?, ?)",
        (token_id, path, ip, user_agent),
    )
    db.commit()
