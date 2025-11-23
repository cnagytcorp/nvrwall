from flask import (
    Blueprint, request, abort, jsonify,
    render_template_string, Response, send_from_directory
)
from .tokens import (
    create_token, revoke_token,
    is_token_valid, log_access
)
# from .nvr import get_grid_frame
import os
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


# --- WALL VIEW (HLS) ---
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
        <title>NVR Wall - CH1</title>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <style>
            html, body {
                margin: 0;
                padding: 0;
                height: 100%;
                background: #000;
                overflow: hidden;
            }
            video {
                width: 100vw;
                height: 100vh;
                object-fit: contain;   /* show full frame, keep aspect, letterbox if needed */
                background: #000;      /* black bars around image */
                display: block;
            }
        </style>
    </head>
    <body>
        <video id="cam1" autoplay muted></video>
        <script>
            const token = "{{ token }}";
            const src = "/hls/ch1.m3u8?token=" + encodeURIComponent(token);
            const video = document.getElementById("cam1");

            if (Hls.isSupported()) {
                const hls = new Hls();
                hls.loadSource(src);
                hls.attachMedia(video);
            } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                video.src = src;
            } else {
                video.outerHTML = "<p style='color:white'>HLS not supported in this browser.</p>";
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, token=token)

# # --- MJPEG STREAM ---
# @bp.get("/stream")
# def stream():
#     token = request.args.get("token", "")
#     token_id = is_token_valid(token)
#     if token_id is None:
#         abort(401, "Invalid or revoked token")

#     log_access(
#         token_id=token_id,
#         path="/stream",
#         ip=request.remote_addr,
#         user_agent=request.headers.get("User-Agent", ""),
#     )

#     def generate():
#         while True:
#             frame = get_grid_frame()
#             encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 80]  # 0–100, default ~95
#             ret, jpeg = cv2.imencode(".jpg", frame, encode_params)

#             if not ret:
#                 continue

#             data = jpeg.tobytes()
#             yield (
#                 b"--frame\r\n"
#                 b"Content-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
#             )
#             time.sleep(0.07)  # ~14 fps

#     return Response(
#         generate(),
#         mimetype="multipart/x-mixed-replace; boundary=frame",
#     )

@bp.get("/hls/<path:filename>")
def serve_hls(filename):
    hls_dir = "/home/enjoy/nvr/hls"  # where ffmpeg writes ch1.m3u8 and .ts segments

    # If this is a playlist, enforce token
    if filename.endswith(".m3u8"):
        token = request.args.get("token", "")
        token_id = is_token_valid(token)
        if token_id is None:
            abort(401, "Invalid or revoked token")

        log_access(
            token_id=token_id,
            path=f"/hls/{filename}",
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
        )

        return send_from_directory(hls_dir, filename)

    # If this is a .ts segment, DO NOT require token (browser doesn't send it)
    return send_from_directory(hls_dir, filename)