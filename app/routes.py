from flask import (
    Blueprint, request, abort, jsonify,
    render_template_string, Response, send_from_directory
)
from .tokens import (
    create_token, revoke_token,
    is_token_valid, log_access
)

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
        <title>NVR Wall - 4 Cameras</title>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <style>
            html, body {
                margin: 0;
                padding: 0;
                height: 100%;
                background: #000;
                overflow: hidden;
            }
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                grid-template-rows: 1fr 1fr;
                width: 100vw;
                height: 100vh;
            }
            .grid video {
                width: 100%;
                height: 100%;
                object-fit: fill;   /* stretch each feed to fill its 16:9 cell */
                background: #000;
                display: block;
            }
        </style>
    </head>
    <body>
        <div class="grid">
            <video id="v1" autoplay muted></video>
            <video id="v2" autoplay muted></video>
            <video id="v3" autoplay muted></video>
            <video id="v4" autoplay muted></video>
        </div>
        <script>
            function setupVideo(id, url) {
                const video = document.getElementById(id);
                if (Hls.isSupported()) {
                    const hls = new Hls();
                    hls.loadSource(url);
                    hls.attachMedia(video);
                } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                    video.src = url;
                } else {
                    video.outerHTML = "<p style='color:white'>HLS not supported.</p>";
                }
            }

            const token = "{{ token }}";

            setupVideo("v1", "/hls/ch1.m3u8?token=" + encodeURIComponent(token));
            setupVideo("v2", "/hls/ch2.m3u8?token=" + encodeURIComponent(token));
            setupVideo("v3", "/hls/ch3.m3u8?token=" + encodeURIComponent(token));
            setupVideo("v4", "/hls/ch4.m3u8?token=" + encodeURIComponent(token));
        </script>
    </body>
    </html>
    """
    return render_template_string(html, token=token)


# --- SERVE HLS FILES ---
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