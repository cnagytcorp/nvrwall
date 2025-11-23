from flask import Flask
from .database import init_db

def create_app():
    app = Flask(__name__)

    # Secret key for sessions (not URL tokens)
    app.config["SECRET_KEY"] = "dev"  # will be overridden in prod

    # Init database (creates schema if missing)
    init_db(app)

    # Register blueprints
    from .routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    return app
