# pomodoro_app/__init__.py
import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import config_by_name, Config

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
limiter = Limiter(key_func=get_remote_address)
csrf = CSRFProtect()

def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_CONFIG', 'development')

    app = Flask(__name__, instance_relative_config=True)

    # --- Load configuration class ---
    selected_config = None
    try:
        selected_config = config_by_name[config_name]()
        app.config.from_object(selected_config)
        print(f" * Loading configuration: {config_name}")
    except KeyError:
        print(f" ! WARNING: Invalid FLASK_CONFIG '{config_name}'. Falling back to development.")
        selected_config = config_by_name['development']()
        app.config.from_object(selected_config)
        config_name = 'development'
    except RuntimeError as e:
        print(f"!!! FATAL CONFIGURATION ERROR: {e}")
        import sys
        sys.exit(f"Configuration Error: {e}")

    # --- Edge case: warn if OPENAI_API_KEY is missing ---
    # (Keep existing code) ...
    if not app.config.get('OPENAI_API_KEY'):
        app.logger.warning(
            "⚠️  OPENAI_API_KEY is not set. "
            "AI Assistant (chat) feature will be disabled. "
            "To enable it, export your key:\n"
            "    export OPENAI_API_KEY='your_key_here'"
        )

    # Load instance config if it exists
    app.config.from_pyfile('config.py', silent=True)

    # --- Logging Setup ---
    # (Keep existing code) ...
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
    csrf.init_app(app)

    from pomodoro_app.main.api_routes import cleanup_old_agent_audio_files
    # --- Clean up temporary agent audio files ---
    with app.app_context():
        cleanup_old_agent_audio_files(
            app.config.get('MAX_AUDIO_FILE_AGE', 3600)
        )

    # Disable rate limiting if testing
    # (Keep existing code) ...
    if app.config.get('TESTING', False) and not app.config.get('RATELIMIT_ENABLED', True):
        limiter.enabled = False
        app.logger.info("Rate limiting disabled for testing.")


    # --- CSRF Handling for Testing ---
    # (Keep existing code) ...
    if not app.config.get('WTF_CSRF_ENABLED', True):
         csrf.exempt_methods = [] # Disable CSRF checks entirely if configured


    # --- START: Add Security Headers (including CSP) ---
    @app.after_request
    def add_security_headers(resp):
        # Content Security Policy (CSP)
        # - default-src 'self': Allows loading resources only from the same origin by default.
        # - script-src 'self' https://cdn.jsdelivr.net: Allows scripts from self and the specified CDN.
        # - style-src 'self' 'unsafe-inline': Allows CSS from self and inline styles (needed for dynamically added styles like agent_chat.js).
        # - img-src 'self' data:: Allows images from self and data URIs (if used).
        # - object-src 'none': Disallows plugins like Flash.
        # - frame-ancestors 'none': Prevents the site from being embedded in iframes (clickjacking protection).
        csp = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net 'unsafe-eval'; " # For Marked/DOMPurify CDN and Chart.js
            "style-src 'self' 'unsafe-inline'; "          # For local CSS and injected chat styles
            "img-src 'self' data:; "                       # Allows local images and data URIs
            "object-src 'none'; "                          # Disallow plugins (Flash, etc.)
            "frame-ancestors 'none'; "                     # Prevent clickjacking
            # Add other directives as needed (e.g., font-src, connect-src, media-src)
            # If you load fonts from Google Fonts, add: font-src 'self' https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
        )
        resp.headers['Content-Security-Policy'] = csp

        # Other Recommended Security Headers
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['X-Frame-Options'] = 'DENY' # Redundant with frame-ancestors 'none', but good defense-in-depth
        resp.headers['X-XSS-Protection'] = '1; mode=block' # For older browsers that support it
        resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Add HSTS header if your site is served over HTTPS
        if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
             resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        return resp
    # --- END: Add Security Headers ---


    # User loader
    from pomodoro_app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from pomodoro_app.auth.routes import auth as auth_bp
    from pomodoro_app.main.routes import main as main_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)

    # Custom error handlers...
    # (Keep existing handlers: 429, CSRFError, 500, 501, 503)
    # ...
    @app.errorhandler(429)
    def ratelimit_handler(e):
        app.logger.warning(f"Rate limit exceeded for {request.remote_addr}: {e.description}")
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=f"Rate limit exceeded: {e.description}"), 429
        return render_template("429.html", error=e.description), 429

    from flask_wtf.csrf import CSRFError
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        app.logger.warning(f"CSRF validation failed: {e.description} for {request.remote_addr} accessing {request.path}")
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=f"CSRF Error: {e.description}. Please refresh the page and try again."), 400
        return render_template('400_csrf.html', error=e.description), 400 # Render dedicated CSRF error page


    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"Internal Server Error: {e}", exc_info=True)
        try:
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
    # --- End error handlers ---

    # ——— Inject chat feature flag into all templates ———
    @app.context_processor
    def inject_chat_status():
        return {
            'chat_enabled': app.config.get('FEATURE_CHAT_ENABLED', False)
        }

    # Register CLI commands
    from .cli import personas as personas_cli, secrets as secrets_cli
    app.cli.add_command(personas_cli)
    app.cli.add_command(secrets_cli)
    return app