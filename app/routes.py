from flask import (
    Blueprint, request, abort, jsonify,
    render_template_string, Response, send_from_directory
)
from .tokens import (
    create_token, revoke_token,
    is_token_valid, log_access
)
from .nvr import get_grid_frame
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


# # --- WALL PAGE (HTML) ---
# @bp.get("/wall")
# def wall():
#     token = request.args.get("token", "")
#     token_id = is_token_valid(token)
#     if token_id is None:
#         abort(401, "Invalid or revoked token")

#     log_access(
#         token_id=token_id,
#         path="/wall",
#         ip=request.remote_addr,
#         user_agent=request.headers.get("User-Agent", ""),
#     )

#     html = """
#     <!doctype html>
#     <html>
#     <head>
#         <title>NVR Wall</title>
#         <style>
#             html, body {
#                 margin: 0;
#                 padding: 0;
#                 height: 100%;
#                 background: #000;
#                 overflow: hidden;
#             }
#             #video {
#                 position: fixed;
#                 top: 50%;
#                 left: 50%;
#                 transform: translate(-50%, -50%);
#                 width: 100vw;
#                 height: auto;
#                 max-height: 100vh;
#                 display: block;
#             }
#         </style>
#     </head>
#     <body>
#         <img id="video" src="/stream?token={{ token }}" alt="NVR Wall">
#         <!-- Press F11 in the browser for real fullscreen -->
#     </body>
#     </html>
#     """
#     return render_template_string(html, token=token)
# @bp.get("/wall")
# def wall():
#     token = request.args.get("token", "")
#     token_id = is_token_valid(token)
#     if token_id is None:
#         abort(401, "Invalid or revoked token")

#     log_access(token_id, "/wall", request.remote_addr, request.headers.get("User-Agent"))

#     html = """
#     <!doctype html>
#     <html>
#     <head>
#         <title>NVR Wall (HLS)</title>
#         <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
#         <style>
#             body {
#                 margin: 0;
#                 background: black;
#                 overflow: hidden;
#             }
#             .grid {
#                 display: grid;
#                 width: 100vw;
#                 height: 100vh;
#                 grid-template-columns: 1fr 1fr;
#                 grid-template-rows: 1fr 1fr;
#             }
#             video {
#                 width: 100%;
#                 height: 100%;
#                 object-fit: cover;
#             }
#         </style>
#     </head>
#     <body>
#         <div class="grid">
#             <video id="v1" autoplay muted></video>
#             <video id="v2" autoplay muted></video>
#             <video id="v3" autoplay muted></video>
#             <video id="v4" autoplay muted></video>
#         </div>
#         <script>
#             function setupVideo(id, url) {
#                 var video = document.getElementById(id);
#                 if (Hls.isSupported()) {
#                     var hls = new Hls();
#                     hls.loadSource(url);
#                     hls.attachMedia(video);
#                 } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
#                     video.src = url;
#                 }
#             }

#             const token = "{{ token }}";

#             setupVideo("v1", "/hls/ch1.m3u8?token=" + token);
#             setupVideo("v2", "/hls/ch2.m3u8?token=" + token);
#             setupVideo("v3", "/hls/ch3.m3u8?token=" + token);
#             setupVideo("v4", "/hls/ch4.m3u8?token=" + token);
#         </script>
#     </body>
#     </html>
#     """
#     return render_template_string(html, token=token)

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
                object-fit: cover;
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