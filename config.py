# config.py
import os
import logging
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Module-level logger
logger = logging.getLogger(__name__)

class Config:
    """Base configuration."""
    # REMOVED default fallback - will be None if not set, enforced in ProductionConfig
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # REMOVED default fallback - will be None if not set, enforced in ProductionConfig
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')  # Optional, remains None if not set

    # Path to JSON file containing agent persona prompts and voices
    AGENT_PERSONA_FILE = os.environ.get(
        'AGENT_PERSONA_FILE',
        os.path.join(basedir, 'agent_personas.json')
    )

    # Optional: Configure logging level
    LOGGING_LEVEL = os.environ.get('LOGGING_LEVEL', 'INFO').upper()

    # Rate Limiter default configuration (can be overridden)
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    # --- Use memory as default, ProductionConfig will override ---
    RATELIMIT_STORAGE_URI = os.environ.get(
        'RATELIMIT_STORAGE_URI', # Allow override via env var for dev/test if needed
        'memory://' # Default to memory for non-production unless overridden
    )

    # Default values for Pomodoro (can be used if needed)
    DEFAULT_WORK_MINUTES = 25
    DEFAULT_BREAK_MINUTES = 5
    POINTS_PER_MINUTE = 10 # Default points per minute for work session

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
        return value # Return the value if it exists

    @staticmethod
    def _mask_url_credentials(url: str) -> str:
        """Return the URL with any user credentials replaced with ***."""
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            # Rebuild netloc without credentials
            netloc = parsed.hostname or ''
            if parsed.port:
                netloc += f':{parsed.port}'
            parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)


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
    # Development uses memory by default unless RATELIMIT_STORAGE_URI is set via env var


class ProductionConfig(Config):
    """Production configuration."""
    FLASK_ENV = 'production'
    DEBUG = False
    # Production rate limits (can still be overridden by RATELIMIT_DEFAULT env var)
    RATELIMIT_DEFAULT = "200 per day;50 per hour" # Explicitly set standard limits

    # +++ MODIFIED: Fail-fast checks + Redis configuration in __init__ +++
    def __init__(self):
        super().__init__()
        logger.info("Applying production config checks...")
        # Ensure required variables are set in the environment for production
        required_vars = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"]
        validated_vars = {}
        for req in required_vars:
            validated_vars[req] = self._assert(req)

        # --- Set the Redis URL specifically for production ---
        # Retrieve the validated REDIS_URL environment variable
        redis_url = validated_vars["REDIS_URL"]
        parsed = urlparse(redis_url)
        if parsed.scheme != "redis" or not parsed.hostname:
            raise RuntimeError("REDIS_URL must be a valid redis:// URI with host")
        # Set the Flask-Limiter config key, overriding the base Config default
        self.RATELIMIT_STORAGE_URI = redis_url
        masked_url = self._mask_url_credentials(redis_url)
        short_url = masked_url[:20] + "..." if len(masked_url) > 20 else masked_url
        logger.info("Rate limit storage URI set to Redis: %s", short_url)

        # Optionally, you could perform a basic check on the Redis URL format here
        logger.info("Production config checks passed.")


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
    # Testing uses memory by default unless RATELIMIT_STORAGE_URI is set via env var


# Dictionary to easily retrieve config class by name
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}