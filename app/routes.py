from flask import Blueprint, request, abort, jsonify
from .tokens import (
    create_token, revoke_token,
    is_token_valid, log_access
)

bp = Blueprint("routes", __name__)

# --- HEALTH CHECK ---
@bp.get("/")
def index():
    return "NVR Wall backend (routes active)", 200


# --- CREATE TOKEN ---
# Example: POST /tokens
# Body: {"description": "garage tablet"}
@bp.post("/tokens")
def api_create_token():
    data = request.get_json(force=True)
    description = data.get("description", "")

    new_tok = create_token(description)
    return jsonify({"token": new_tok})


# --- REVOKE TOKEN ---
# Example: POST /tokens/revoke
# Body: {"token": "xxxxx"}
@bp.post("/tokens/revoke")
def api_revoke_token():
    data = request.get_json(force=True)
    tok = data.get("token")

    if not tok:
        abort(400, "missing token")

    revoke_token(tok)
    return jsonify({"status": "revoked"})


# --- PROTECTED ENDPOINT EXAMPLE ---
@bp.get("/wall")
def wall():
    token = request.args.get("token", "")
    token_id = is_token_valid(token)

    if token_id is None:
        abort(401, "Invalid or revoked token")

    # Log usage
    log_access(
        token_id=token_id,
        path="/wall",
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")
    )

    return "Token OK — full wall will go here", 200
