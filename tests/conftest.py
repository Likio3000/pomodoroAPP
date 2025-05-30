# tests/conftest.py
import pytest
import os
from pomodoro_app import create_app, db
from pomodoro_app.models import User

# Define a test configuration class
class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory SQLite for tests
    SECRET_KEY = 'test-secret-key' # Use a specific key for tests
    WTF_CSRF_ENABLED = False # Disable CSRF forms for easier testing (can test separately if needed)
    LOGIN_DISABLED = False # Ensure login is enabled unless specifically testing disabled login
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SERVER_NAME = 'localhost'  # Added for URL building in tests
    DISABLE_RATE_LIMIT = True  # Disable rate limiting by default for fast, isolated tests

class RateLimitTestConfig(TestConfig):
    DISABLE_RATE_LIMIT = False  # Enable rate limiting for specific tests

@pytest.fixture(scope='module')
def test_app():
    """Create and configure a new app instance for each test module."""
    app = create_app(TestConfig) # Pass the test config
    yield app # 'yield' makes it available to tests

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
