from flask import (
    Blueprint, request, abort, jsonify,
    render_template_string, Response, send_from_directory, current_app
)
import os

from .tokens import (
    is_token_valid,
    log_access,
    list_tokens,
    revoke_token,
    create_token,
)

bp = Blueprint("routes", __name__)

# Absolute path to your HLS folder
HLS_DIR = "/home/enjoy/nvr/hls"

# --- HEALTH CHECK ---
@bp.get("/")
def index():
    return "NVR Wall backend (routes + tokens + NVR active)", 200


# --- watchdog ---
@bp.get("/health")
def health():
    return jsonify(status="ok"), 200


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
    """
    Serve HLS playlists and segments.

    - For .m3u8: check token + log access (hits DB)
    - For .ts: no token/DB check (avoid DB lock)
    - Disable caching to avoid stale HLS
    """
    # Only validate/log for playlists
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

    full_path = os.path.join(HLS_DIR, filename)
    if not os.path.isfile(full_path):
        abort(404)

    resp = send_from_directory(HLS_DIR, filename)

    # Stop browser from caching HLS files aggressively
    resp.cache_control.no_store = True
    resp.cache_control.must_revalidate = True
    resp.expires = 0

    return resp


# --- ADMIN: LIST TOKENS ---
@bp.get("/admin/tokens")
def admin_tokens():
    """
    Very simple HTML page listing all tokens and basic info.
    No auth yet – intended for LAN use. Lock down with nginx or VPN if needed.
    """
    rows = list_tokens()

    html = """
    <!doctype html>
    <html>
    <head>
        <title>NVR Tokens Admin</title>
        <style>
            body { font-family: system-ui, sans-serif; background:#0f172a; color:#e5e7eb; padding:20px; }
            table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
            th, td { border: 1px solid #374151; padding: 6px 8px; font-size: 13px; }
            th { background:#111827; text-align:left; }
            tr:nth-child(even) { background:#111827; }
            tr:nth-child(odd) { background:#020617; }
            .badge { padding: 2px 6px; border-radius: 999px; font-size: 11px; }
            .ok { background:#065f46; }
            .revoked { background:#7f1d1d; }
            .expired { background:#92400e; }
            a { color:#60a5fa; text-decoration:none; }
            a:hover { text-decoration:underline; }
            .token { font-family: monospace; font-size: 11px; }
        </style>
    </head>
    <body>
        <h1>Token Admin</h1>
        <p>Tokens used to access the NVR wall. Revoke tokens you no longer want to be valid.</p>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Description</th>
                    <th>Token</th>
                    <th>Created</th>
                    <th>Expires</th>
                    <th>Last Used</th>
                    <th>Status</th>
                    <th>Revoke</th>
                </tr>
            </thead>
            <tbody>
            {% for t in tokens %}
                <tr>
                    <td>{{ t.id }}</td>
                    <td>{{ t.description or '' }}</td>
                    <td class="token">{{ t.token }}</td>
                    <td>{{ t.created_at }}</td>
                    <td>{{ t.expires_at or '' }}</td>
                    <td>{{ t.last_access_at or t.last_used_at or '' }}</td>
                    <td>
                        {% if t.revoked %}
                            <span class="badge revoked">revoked</span>
                        {% elif t.is_expired %}
                            <span class="badge expired">expired</span>
                        {% else %}
                            <span class="badge ok">active</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if not t.revoked %}
                            <a href="/admin/tokens/revoke?id={{ t.id }}">Revoke</a>
                        {% endif %}
                    </td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
    </body>
    </html>
    """
    return render_template_string(html, tokens=rows)


# --- ADMIN: REVOKE TOKEN ---
@bp.get("/admin/tokens/revoke")
def admin_revoke_token():
    tid = request.args.get("id")
    if not tid:
        abort(400, "id is required")
    try:
        token_id = int(tid)
    except ValueError:
        abort(400, "invalid id")

    revoke_token(token_id)
    # redirect back to list
    from flask import redirect, url_for
    return redirect(url_for("routes.admin_tokens"))
