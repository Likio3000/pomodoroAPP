# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

class Config:
    """Base configuration."""
    # REMOVED default fallback - will be None if not set, enforced in ProductionConfig
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # REMOVED default fallback - will be None if not set, enforced in ProductionConfig
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')  # Optional, remains None if not set

    # Optional: Configure logging level
    LOGGING_LEVEL = os.environ.get('LOGGING_LEVEL', 'INFO').upper()

    # Rate Limiter default configuration (can be overridden)
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get(
        'RATELIMIT_STORAGE_URI',
        'memory://'
    )  # 'memory://' for single process, consider redis for multi-process

    # Default values for Pomodoro (can be used if needed)
    DEFAULT_WORK_MINUTES = 25
    DEFAULT_BREAK_MINUTES = 5

    # Control feature flags if needed
    FEATURE_CHAT_ENABLED = bool(OPENAI_API_KEY)  # Automatically enable chat if key exists

    # --- NEW: TTS Toggle Flag ---
    TTS_ENABLED = os.environ.get('TTS_ENABLED', 'true').lower() in ('1', 'true', 'yes')

    # +++ NEW: Fail-fast helper method +++
    @staticmethod
    def _assert(var_name: str):
        """Helper to ensure a required environment variable is set."""
        value = os.environ.get(var_name)
        if not value:
            raise RuntimeError(f"Required environment variable '{var_name}' is not set.")
        # Optional: Add more checks here if needed, e.g., minimum length for SECRET_KEY
        # if var_name == 'SECRET_KEY' and len(value) < 16:
        #     raise RuntimeError(f"'{var_name}' must be at least 16 characters long.")


class DevelopmentConfig(Config):
    """Development configuration."""
    FLASK_ENV = 'development'
    DEBUG = True
    # +++ ADDED BACK: Fallback SECRET_KEY specifically for development +++
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-secret-key-CHANGE-ME')
    # +++ ADDED BACK: Use a separate fallback DB for development +++
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(basedir, 'pomodoro_app', 'pomodoro-dev.db')
    )
    # Less strict rate limits for development/testing
    RATELIMIT_DEFAULT = "500 per day;100 per hour;20 per minute"


class ProductionConfig(Config):
    """Production configuration."""
    FLASK_ENV = 'production'
    DEBUG = False

    # +++ NEW: Fail-fast checks during initialization +++
    def __init__(self):
        # Note: super().__init__() is not strictly needed here as base Config.__init__ does nothing,
        # but included for robustness if the base init changes later.
        super().__init__()
        print(" * Applying production config checks...") # Optional: Indicate checks are running
        # Ensure required variables are set in the environment for production
        for req in ("SECRET_KEY", "DATABASE_URL"):
            self._assert(req)
        print(" * Production config checks passed.") # Optional: Indicate checks passed


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    # Use in-memory SQLite database for tests or a dedicated test file
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing forms
    SECRET_KEY = 'test-secret-key' # Explicitly set for tests, overrides base
    # Disable rate limiting for tests usually
    RATELIMIT_ENABLED = False


# Dictionary to easily retrieve config class by name
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}