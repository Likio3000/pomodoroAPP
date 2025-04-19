# pomodoro_app/__init__.py
import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import config_by_name, Config # Keep Config import for reference if needed, but specific checks removed

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
limiter = Limiter(key_func=get_remote_address)

def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_CONFIG', 'development')

    app = Flask(__name__, instance_relative_config=True)

    # --- Load configuration class ---
    selected_config = None
    try:
        # Instantiate the config class - THIS is where ProductionConfig.__init__ runs its checks
        selected_config = config_by_name[config_name]()
        app.config.from_object(selected_config)
        print(f" * Loading configuration: {config_name}")
    except KeyError:
        print(f" ! WARNING: Invalid FLASK_CONFIG '{config_name}'. Falling back to development.")
        # Instantiate development config if specified one fails
        selected_config = config_by_name['development']()
        app.config.from_object(selected_config)
        config_name = 'development' # Update config_name to reflect the actual loaded config
    except RuntimeError as e:
        # Catch the RuntimeError raised by _assert in ProductionConfig.__init__
        print(f"!!! FATAL CONFIGURATION ERROR: {e}")
        # Optionally log more details here
        # Exit the application immediately as it cannot run without required config
        import sys
        sys.exit(f"Configuration Error: {e}")

    # --- Edge case: warn if OPENAI_API_KEY is missing ---
    # This check remains relevant as OPENAI_API_KEY is optional
    if not app.config.get('OPENAI_API_KEY'):
        app.logger.warning(
            "⚠️  OPENAI_API_KEY is not set. "
            "AI Assistant (chat) feature will be disabled. "
            "To enable it, export your key:\n"
            "    export OPENAI_API_KEY='your_key_here'"
        )


    # Load instance config if it exists (allows overriding settings locally)
    app.config.from_pyfile('config.py', silent=True)

    # --- Logging Setup ---
    log_level = getattr(logging, app.config.get('LOGGING_LEVEL', 'INFO'), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s'
    )
    app.logger.info(f"Flask app created with config '{config_name}'")

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # Disable rate limiting if testing
    if app.config.get('TESTING', False) and not app.config.get('RATELIMIT_ENABLED', True):
        limiter.enabled = False
        app.logger.info("Rate limiting disabled for testing.")

    # User loader
    from pomodoro_app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        # Use db.session.get for primary key lookups (more efficient)
        return db.session.get(User, int(user_id))

    # Register blueprints
    from pomodoro_app.auth.routes import auth as auth_bp
    from pomodoro_app.main.routes import main as main_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)

    # Custom error handlers...
    @app.errorhandler(429)
    def ratelimit_handler(e):
        app.logger.warning(f"Rate limit exceeded for {request.remote_addr}: {e.description}")
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=f"Rate limit exceeded: {e.description}"), 429
        return render_template("429.html", error=e.description), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"Internal Server Error: {e}", exc_info=True)
        try:
            # Rollback potentially broken DB session
            db.session.rollback()
            app.logger.info("Database session rolled back due to 500 error.")
        except Exception as rollback_err:
            app.logger.error(f"Error during DB session rollback on 500 error: {rollback_err}", exc_info=True)
        return render_template("500.html"), 500

    @app.errorhandler(501)
    def not_implemented_error(e):
        app.logger.error(f"Not Implemented (501): Feature requested at {request.path}. Description: {e.description}", exc_info=True)
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=f"Not Implemented: {e.description or 'Feature not available'}"), 501
        return render_template("501.html", error=e.description), 501

    @app.errorhandler(503)
    def service_unavailable_error(e):
        app.logger.error(f"Service Unavailable (503): Error accessing {request.path}. Description: {e.description}", exc_info=True)
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=f"Service Unavailable: {e.description or 'The service is temporarily unavailable'}"), 503
        return render_template("503.html", error=e.description), 503

    # --- Inject chat feature flag into all templates ---
    @app.context_processor
    def inject_chat_status():
        # This uses the already loaded app.config
        return {
            'chat_enabled': app.config.get('FEATURE_CHAT_ENABLED', False)
        }

    return app