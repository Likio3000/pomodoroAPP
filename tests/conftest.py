# tests/conftest.py
import pytest
import os
from pomodoro_app import create_app, db, limiter
from pomodoro_app.models import User

# Define a test configuration class
class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # Use in-memory SQLite for tests
    SECRET_KEY = 'test-secret-key'  # Use a specific key for tests
    WTF_CSRF_ENABLED = False  # Disable CSRF forms for easier testing (can test separately if needed)
    LOGIN_DISABLED = False  # Ensure login is enabled unless specifically testing disabled login
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SERVER_NAME = 'localhost'  # Added for URL building in tests
    RATELIMIT_ENABLED = False  # Disable rate limiting by default

class RateLimitTestConfig(TestConfig):
    RATELIMIT_ENABLED = True  # Enable rate limiting for specific tests

@pytest.fixture(scope='module')
def test_app():
    """Create and configure a new app instance for each test module."""
    app = create_app('testing')
    app.config.from_object(TestConfig)
    yield app

@pytest.fixture(scope='module')
def test_client(test_app):
    """Create a test client for the app."""
    return test_app.test_client()

@pytest.fixture(scope='module')
def init_database(test_app):
    """Create the database and the database table(s)."""
    with test_app.app_context():
        db.create_all()
        yield db # Make the db instance available to tests if needed
        db.drop_all() # Clean up the DB after tests run in the module

@pytest.fixture(scope='function')
def clean_db(test_app, init_database):
    with test_app.app_context():
        yield init_database


@pytest.fixture(scope='function')
def logged_in_user(test_app, test_client, clean_db):
    from werkzeug.security import generate_password_hash
    from pomodoro_app.models import User
    hashed_pw = generate_password_hash('testpassword', method='pbkdf2:sha256')
    user = User(email='test@example.com', name='Test User', password=hashed_pw)

    with test_app.app_context():
        db.session.add(user)
        db.session.commit()

    # Log in the user using the test client
    test_client.post('/auth/login', data=dict(
        email='test@example.com',
        password='testpassword'
    ), follow_redirects=True)

    yield test_client

    # Optionally log out and clean up after test
    test_client.get('/auth/logout', follow_redirects=True)
    with test_app.app_context():
        db.session.delete(user)
        db.session.commit()


@pytest.fixture(scope='module')
def rate_limit_app():
    """App instance with rate limiting enabled."""
    app = create_app('development')
    app.config.from_object(RateLimitTestConfig)
    yield app
    limiter.enabled = False


@pytest.fixture(scope='module')
def rate_limit_test_client(rate_limit_app):
    """Test client using rate limit config."""
    return rate_limit_app.test_client()


@pytest.fixture(scope='module')
def init_rl_database(rate_limit_app):
    with rate_limit_app.app_context():
        db.create_all()
        yield db
        db.drop_all()


@pytest.fixture(scope='function')
def clean_rl_db(rate_limit_app, init_rl_database):
    with rate_limit_app.app_context():
        yield init_rl_database


@pytest.fixture(scope='function')
def logged_in_user_rate_limit(rate_limit_app, rate_limit_test_client, clean_rl_db):
    from werkzeug.security import generate_password_hash
    hashed_pw = generate_password_hash('testpassword', method='pbkdf2:sha256')
    user = User(email='test@example.com', name='Test User', password=hashed_pw)

    with rate_limit_app.app_context():
        db.session.add(user)
        db.session.commit()

    rate_limit_test_client.post('/auth/login', data=dict(
        email='test@example.com',
        password='testpassword'
    ), follow_redirects=False)

    yield rate_limit_test_client

    rate_limit_test_client.get('/auth/logout', follow_redirects=True)
    with rate_limit_app.app_context():
        db.session.delete(user)
        db.session.commit()
