from flask import (
    Blueprint, request, abort, jsonify,
    render_template_string, Response, send_from_directory
)
from .tokens import (
    create_token, revoke_token,
    is_token_valid, log_access
)
import os
from flask import current_app

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
                width: 100%;
                height: 100%;
                background: #000;
                overflow: hidden;
            }
            .row {
                display: flex;
                width: 100vw;
                height: 50vh;      /* two rows: each is half screen height */
            }
            .row video {
                flex: 1 1 50%;      /* each video half the row width */
                height: 100%;
                width: 50%;
                object-fit: fill;   /* stretch to fill its quadrant */
                background: #000;
                display: block;
            }
        </style>
    </head>
    <body>
        <div class="row">
            <video id="v1" autoplay muted></video>
            <video id="v2" autoplay muted></video>
        </div>
        <div class="row">
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
    token = request.args.get("token", "")

    # Only hit the database for playlists, NOT for each .ts segment
    if filename.endswith(".m3u8"):
        token_id = is_token_valid(token)
        if token_id is None:
            abort(401, "Invalid or revoked token")

        log_access(
            token_id=token_id,
            path=f"/hls/{filename}",
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
        )

    # serve static file
    full_path = os.path.join(current_app.config["HLS_ROOT"], filename)
    if not os.path.isfile(full_path):
        abort(404)

    resp = send_from_directory(current_app.config["HLS_ROOT"], filename)

    # disable caching (see section 2)
    resp.cache_control.no_store = True
    resp.cache_control.must_revalidate = True
    resp.expires = 0

    return resp
