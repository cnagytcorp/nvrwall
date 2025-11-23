from flask import (
    Blueprint, request, abort, jsonify,
    render_template_string, Response, send_from_directory,
    current_app, session, redirect, url_for
)

import os

from .tokens import (
    is_token_valid,
    log_access,
    list_tokens,
    revoke_token,
    create_token,
    verify_admin_password,
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


# --- ADMIN AUTH CHECK ---
def is_admin_logged_in() -> bool:
    return session.get("is_admin", False) is True


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        if verify_admin_password(password):
            session["is_admin"] = True
            next_url = request.args.get("next") or url_for("routes.admin_tokens")
            return redirect(next_url)
        else:
            error = "Invalid admin password"

    html = """
    <!doctype html>
    <html>
    <head>
        <title>Admin Login</title>
        <style>
            body { font-family: system-ui, sans-serif; background:#0f172a; color:#e5e7eb; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
            .box { background:#020617; padding:24px 28px; border-radius:12px; box-shadow:0 10px 30px rgba(0,0,0,0.5); width:320px; }
            h1 { font-size:20px; margin-top:0; margin-bottom:12px; }
            label { display:block; font-size:13px; margin-bottom:4px; }
            input[type=password] { width:100%; padding:8px; border-radius:6px; border:1px solid #374151; background:#0b1120; color:#e5e7eb; }
            button { margin-top:12px; width:100%; padding:8px; border:none; border-radius:6px; background:#2563eb; color:white; font-weight:500; cursor:pointer; }
            button:hover { background:#1d4ed8; }
            .error { color:#f87171; font-size:13px; margin-top:8px; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>Admin Login</h1>
            <form method="post">
                <label for="user">Admin username</label>
                <input id="user" name="user" type="text" required />
                <label for="password">Admin password</label>
                <input id="password" name="password" type="password" required />
                {% if error %}
                    <div class="error">{{ error }}</div>
                {% endif %}
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, error=error)

# --- ADMIN LOGOUT ---
@bp.get("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("routes.admin_login"))


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
@bp.route("/admin/tokens", methods=["GET", "POST"])
def admin_tokens():
    """
    Admin UI:
    - View tokens
    - Add new token via form (description + days_valid)
    - Revoke via separate route
    """
    if not is_admin_logged_in():
        return redirect(url_for("routes.admin_login", next=request.path))

    new_token_value = None

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        days_raw = request.form.get("days_valid", "").strip()

        days_valid = None
        if days_raw:
            try:
                days_valid = int(days_raw)
            except ValueError:
                days_valid = None

        new_token_value = create_token(description, days_valid=days_valid)

    rows = list_tokens()

    html = """
    <!doctype html>
    <html>
    <head>
        <title>NVR Tokens Admin</title>
        <style>
            body { font-family: system-ui, sans-serif; background:#0f172a; color:#e5e7eb; padding:20px; }
            h1 { margin-top:0; }
            a { color:#60a5fa; text-decoration:none; }
            a:hover { text-decoration:underline; }
            table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
            th, td { border: 1px solid #374151; padding: 6px 8px; font-size: 13px; }
            th { background:#111827; text-align:left; }
            tr:nth-child(even) { background:#111827; }
            tr:nth-child(odd) { background:#020617; }
            .badge { padding: 2px 6px; border-radius: 999px; font-size: 11px; }
            .ok { background:#065f46; }
            .revoked { background:#7f1d1d; }
            .expired { background:#92400e; }
            .token { font-family: monospace; font-size: 11px; }
            .top-bar { display:flex; justify-content:space-between; align-items:center; }
            .form-row { margin-top:1rem; padding:12px; background:#020617; border-radius:8px; border:1px solid #1f2937; }
            label { font-size:13px; display:block; margin-bottom:4px; }
            input[type=text], input[type=number] { padding:6px; border-radius:6px; border:1px solid #374151; background:#0b1120; color:#e5e7eb; width:100%; max-width:260px; }
            button { padding:6px 12px; border:none; border-radius:6px; background:#2563eb; color:white; font-size:13px; cursor:pointer; }
            button:hover { background:#1d4ed8; }
            .new-token-box { margin-top:10px; padding:8px; background:#022c22; border-radius:6px; font-family:monospace; font-size:12px; }
        </style>
    </head>
    <body>
        <div class="top-bar">
            <h1>Token Admin</h1>
            <div>
                <a href="/admin/logout">Logout</a>
            </div>
        </div>

        <div class="form-row">
            <form method="post">
                <div style="display:flex; gap:16px; flex-wrap:wrap; align-items:flex-end;">
                    <div>
                        <label for="description">Description</label>
                        <input id="description" name="description" type="text" placeholder="e.g. Upstairs TV" />
                    </div>
                    <div>
                        <label for="days_valid">Valid for (days)</label>
                        <input id="days_valid" name="days_valid" type="number" min="1" placeholder="30" />
                    </div>
                    <div>
                        <button type="submit">Create Token</button>
                    </div>
                </div>
            </form>

            {% if new_token %}
                <div class="new-token-box">
                    New token (copy & save now): {{ new_token }}
                </div>
            {% endif %}
        </div>

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
    return render_template_string(html, tokens=rows, new_token=new_token_value)


# --- ADMIN: REVOKE TOKEN ---
@bp.get("/admin/tokens/revoke")
def admin_revoke_token():
    if not is_admin_logged_in():
        return redirect(url_for("routes.admin_login", next=request.path))

    tid = request.args.get("id")
    if not tid:
        abort(400, "id is required")
    try:
        token_id = int(tid)
    except ValueError:
        abort(400, "invalid id")

    revoke_token(token_id)
    return redirect(url_for("routes.admin_tokens"))

