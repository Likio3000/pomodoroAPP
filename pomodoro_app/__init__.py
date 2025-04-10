# pomodoro_app/__init__.py
import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
#from flask_migrate import Migrate # Import Flask-Migrate

# Import config classes
from config import config_by_name

# Initialize extensions (to be used later in factory)
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info' # Optional: style flash message

# Initialize Migrate (will be configured with app and db in factory)
#migrate = Migrate()

# Set up Flask-Limiter (will be configured in factory)
limiter = Limiter(key_func=get_remote_address)


def create_app(config_name=None): # config_name e.g., 'development', 'production'
    if config_name is None:
         # Determine config from environment variable, default to development
         config_name = os.getenv('FLASK_CONFIG', 'development')

    app = Flask(__name__, instance_relative_config=True) # Enable instance folder

    # --- Configuration ---
    try:
        app.config.from_object(config_by_name[config_name])
        print(f" * Loading configuration: {config_name}") # Log which config is loaded
    except KeyError:
         print(f" ! WARNING: Invalid FLASK_CONFIG name '{config_name}'. Falling back to 'development'.")
         app.config.from_object(config_by_name['development'])


    # --- !! ADD PRODUCTION CONFIGURATION CHECK HERE !! ---
    if config_name == 'production':
        if not app.config.get('SQLALCHEMY_DATABASE_URI'):
             # Cannot reliably use app.logger here yet if logging hasn't been set up
             print("CRITICAL ERROR: No SQLALCHEMY_DATABASE_URI is configured for the production environment!")
             raise ValueError("Production environment requires SQLALCHEMY_DATABASE_URI to be set.")
        # Add other essential production checks if needed (e.g., SECRET_KEY strength)
        # if not app.config.get('SECRET_KEY') or app.config['SECRET_KEY'] == 'default-dev-secret-key-CHANGE-ME':
        #     print("CRITICAL ERROR: Default or missing SECRET_KEY in production!")
        #     raise ValueError("Production environment requires a strong, unique SECRET_KEY.")


   # Load instance config if it exists
    app.config.from_pyfile('config.py', silent=True)
    # --- End Configuration Loading ---


    # --- Logging Setup ---
    log_level = getattr(logging, app.config.get('LOGGING_LEVEL', 'INFO'), logging.INFO)
    logging.basicConfig(level=log_level,
                        format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')
    # Add production logging handlers if needed...
    app.logger.info(f"Flask App '{__name__}' created with config '{config_name}'")
    # --- End Logging Setup ---


    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
  # migrate.init_app(app, db) # Initialize Flask-Migrate

    # Disable rate limiting if configured for testing
    if app.config.get('TESTING', False) and app.config.get('RATELIMIT_ENABLED', True) is False:
         limiter.enabled = False
         app.logger.info("Rate limiting disabled for testing.")


    # Import models *after* db is initialized
    from pomodoro_app.models import User, PomodoroSession, ActiveTimerState

    @login_manager.user_loader
    def load_user(user_id):
         # Use session.get for primary key lookup
         return db.session.get(User, int(user_id))


    # Register blueprints
    from pomodoro_app.auth.routes import auth as auth_blueprint
    from pomodoro_app.main.routes import main as main_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    app.register_blueprint(main_blueprint, url_prefix='/')

    # Custom error handler for rate limiting (429 error)
    @app.errorhandler(429)
    def ratelimit_handler(e):
        app.logger.warning(f"Rate limit exceeded for {request.remote_addr}: {e.description}")
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error=f"Rate limit exceeded: {e.description}"), 429
        return render_template("429.html", error=e.description), 429

    # Custom error handler for general server errors (500)
    @app.errorhandler(500)
    def internal_server_error(e):
        # ... (error handler code remains the same) ...
        app.logger.error(f"Internal Server Error: {e}", exc_info=True)
        try:
            db.session.rollback() # Rollback potentially broken DB session
            app.logger.info("Database session rolled back due to 500 error.")
        except Exception as rollback_err:
            app.logger.error(f"Error during DB session rollback on 500 error: {rollback_err}", exc_info=True)
        return render_template("500.html"), 500

    # --- Database Initialization for "Delete & Recreate" Workflow ---
 #   # Use db.create_all() ONLY for initial setup or dev reset workflow
 #   if app.config.get('DEBUG'): # Check if in development/debug mode
 #       with app.app_context():
 #           # Construct the expected DB file path from the URI
 #           db_path_str = app.config.get('SQLALCHEMY_DATABASE_URI', '')
 #           db_file = None
 #           if db_path_str.startswith('sqlite:///'):
 #                path_part = db_path_str.split('///', 1)[1]
 #                # Handle absolute vs relative paths, consider instance folder
 #                if not os.path.isabs(path_part):
 #                     # Assume relative to instance folder if using instance_relative_config=True
 #                     db_file = os.path.join(app.instance_path, path_part)
 #                else:
 #                     db_file = path_part
#
 #           # Only run create_all if it's a file path and the file doesn't exist
 #           if db_file and not os.path.exists(db_file):
 #                 # Ensure the directory exists (especially for instance folder)
 #                 db_dir = os.path.dirname(db_file)
 #                 if not os.path.exists(db_dir):
 #                      try:
 #                           os.makedirs(db_dir)
 #                           app.logger.info(f"Created directory for database: {db_dir}")
 #                      except OSError as e:
 #                           app.logger.error(f"Failed to create database directory {db_dir}: {e}")
 #                 app.logger.info(f"Development mode: Database file not found at {db_file}. Running db.create_all()...")
 #                 try:
 #                      db.create_all()
 #                      app.logger.info("Development mode: Tables created successfully.")
 #                 except Exception as create_err:
 #                      app.logger.error(f"Development mode: Error running db.create_all(): {create_err}", exc_info=True)
#
 #           elif db_file:
 #                 app.logger.debug(f"Development mode: Database file {db_file} already exists. Skipping db.create_all().")
 #           else:
 #                 app.logger.warning("Development mode: Could not determine SQLite file path or not using SQLite file URI. Skipping automatic db.create_all(). Run manually if needed.")


    return app