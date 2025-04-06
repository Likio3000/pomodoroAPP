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

@pytest.fixture(scope='function') # Use 'function' scope if you need clean db per test
def clean_db(init_database):
     """Ensure a clean database for each test function."""
     with init_database.app.app_context():
        # Optionally add code here to clear specific tables if needed between tests
        # For simple cases, init_database's module scope drop_all might be enough
        yield init_database
        # db.session.remove() # Optional: close session if needed

# You can add more fixtures, e.g., for creating a logged-in user
@pytest.fixture(scope='function')
def logged_in_user(test_client, clean_db):
     """Fixture to register and log in a user."""
     # You might need to adjust hashing if using bcrypt differently
     from werkzeug.security import generate_password_hash
     hashed_pw = generate_password_hash('testpassword', method='pbkdf2:sha256')
     user = User(email='test@example.com', name='Test User', password=hashed_pw)

     with clean_db.app.app_context():
         db.session.add(user)
         db.session.commit()

     # Log in the user using the test client
     test_client.post('/auth/login', data=dict(
         email='test@example.com',
         password='testpassword'
     ), follow_redirects=True)

     yield test_client # Return the client, now logged in

     # Clean up: logout after test (optional, as client state might reset anyway)
     test_client.get('/auth/logout', follow_redirects=True)
     # Clean up: delete user if needed per test function (or rely on clean_db/init_database)
     with clean_db.app.app_context():
         db.session.delete(user)
         db.session.commit()