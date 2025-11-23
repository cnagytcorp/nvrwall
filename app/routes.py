from flask import (
    Blueprint, request, abort, jsonify,
    render_template_string, Response
)
from .tokens import (
    create_token, revoke_token,
    is_token_valid, log_access
)
from .nvr import get_grid_frame
import cv2
import time

bp = Blueprint("routes", __name__)


# --- HEALTH CHECK ---
@bp.get("/")
def index():
    return "NVR Wall backend (routes + tokens + NVR active)", 200


# --- TOKEN: CREATE ---
@bp.post("/tokens")
def api_create_token():
    data = request.get_json(force=True, silent=True) or {}
    description = data.get("description", "")
    new_tok = create_token(description)
    return jsonify({"token": new_tok})


# --- TOKEN: REVOKE ---
@bp.post("/tokens/revoke")
def api_revoke_token():
    data = request.get_json(force=True, silent=True) or {}
    tok = data.get("token")
    if not tok:
        abort(400, "missing token")

    revoke_token(tok)
    return jsonify({"status": "revoked"})


# --- WALL PAGE (HTML) ---
@bp.get("/wall")
def wall():
    token = request.args.get("token", "")
    token_id = is_token_valid(token)
    if token_id is None:
        abort(401, "Invalid or revoked token")

    log_access(
        token_id=token_id,
        path="/wall",
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
    )

    html = """
    <!doctype html>
    <html>
    <head>
        <title>NVR Wall</title>
        <style>
            html, body {
                margin: 0;
                padding: 0;
                height: 100%;
                background: #000;
                overflow: hidden;
            }
            #video {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 100vw;
                height: auto;
                max-height: 100vh;
                display: block;
            }
        </style>
    </head>
    <body>
        <img id="video" src="/stream?token={{ token }}" alt="NVR Wall">
        <!-- Press F11 in the browser for real fullscreen -->
    </body>
    </html>
    """
    return render_template_string(html, token=token)


# --- MJPEG STREAM ---
@bp.get("/stream")
def stream():
    token = request.args.get("token", "")
    token_id = is_token_valid(token)
    if token_id is None:
        abort(401, "Invalid or revoked token")

    log_access(
        token_id=token_id,
        path="/stream",
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
    )

    def generate():
        while True:
            frame = get_grid_frame()
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 80]  # 0–100, default ~95
            ret, jpeg = cv2.imencode(".jpg", frame, encode_params)

            if not ret:
                continue

            data = jpeg.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            )
            time.sleep(0.07)  # ~14 fps

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
