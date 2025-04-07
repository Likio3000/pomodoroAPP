# pomodoro_app/__init__.py
import os  # <-- Import the os module
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize extensions (to be used later in factory)
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

# Set up Flask-Limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]  # You can adjust these defaults as needed
)

def create_app(config_object=None): # Optional: Pass a config object for testing
    app = Flask(__name__, instance_relative_config=True) # Consider using instance folder

    # --- Configuration ---
    # Load default config (can be empty or contain non-sensitive defaults)
    # app.config.from_object('config.DefaultConfig') # Example if you use a config file

    # Load secret key from environment variable
    # Provide a default (INSECURE) key ONLY for convenience in local dev if the var isn't set
    # Ensure the real key is set in your production/staging environments!
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-please-change')

    # Load other config
    # Prefer loading DB URI from env var too
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///pomodoro.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Optional: Load config from instance folder (for sensitive data not in Git)
    # app.config.from_pyfile('config.py', silent=True)

    # Optional: Override with a specific config object (useful for tests)
    if config_object:
        app.config.from_object(config_object)
    # --- End Configuration ---

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app) 

    # Import models here so that they are registered with SQLAlchemy
    from pomodoro_app.models import User

    # User loader function for Flask-Login: load user by ID
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from pomodoro_app.auth.routes import auth as auth_blueprint
    from pomodoro_app.main.routes import main as main_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth') # Add prefixes for clarity
    app.register_blueprint(main_blueprint, url_prefix='/') # Main routes usually at root

        # Custom error handler for rate limiting (429 error)
    @app.errorhandler(429)
    def ratelimit_handler(e):
        # If the request prefers JSON, send a JSON response:
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error="Too many requests. Please try again later."), 429
        # Otherwise, render a custom HTML page:
        return render_template("429.html", error=e.description), 429

    # Create database tables if not already created (can be moved to migration script)
    with app.app_context():
        # Consider using Flask-Migrate instead for production
        db.create_all()

    return app