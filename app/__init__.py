from flask import Flask
from .tokens import init_app as init_tokens, init_db


def create_app():
    app = Flask(__name__)

    # Secret key for sessions (not URL tokens)
    app.config["SECRET_KEY"] = "dev"  # change in production

    # Setup SQLite teardown/connection handling
    init_tokens(app)

    # Initialize database schema (1-time run, safe to call many times)
    init_db()

    # Register routes
    from .routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    return app
