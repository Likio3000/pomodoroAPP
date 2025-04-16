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
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-secret-key-CHANGE-ME')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Define database fallback for development if DATABASE_URL is not set
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(basedir, 'pomodoro_app', 'pomodoro-dev.db')
    )
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')  # Will be None if not set

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


class DevelopmentConfig(Config):
    """Development configuration."""
    FLASK_ENV = 'development'
    DEBUG = True
    # Use a separate DB for development
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
    # No runtime logic here—checks moved to create_app()


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    # Use in-memory SQLite database for tests or a dedicated test file
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing forms
    SECRET_KEY = 'test-secret-key'
    # Disable rate limiting for tests usually
    RATELIMIT_ENABLED = False


# Dictionary to easily retrieve config class by name
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}
