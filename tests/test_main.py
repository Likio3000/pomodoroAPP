# tests/test_main.py
from flask import url_for
from pomodoro_app.models import PomodoroSession # Import if needed
from pomodoro_app import db


# Test index page for anonymous user
def test_index_anonymous(test_client, init_database):
    response = test_client.get(url_for('main.index'))
    assert response.status_code == 200
    assert b'Welcome to Pomodoro Tracker' in response.data
    assert b'Login' in response.data
    assert b'Register' in response.data

# Test index page redirects for logged-in user
def test_index_logged_in(logged_in_user): # Use fixture
    response = logged_in_user.get(url_for('main.index'), follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data # Should redirect to dashboard

# Test dashboard access requires login
def test_dashboard_requires_login(test_client, init_database):
    response = test_client.get(url_for('main.dashboard'), follow_redirects=True)
    assert response.status_code == 200
    assert b'Login' in response.data # Should redirect to login page

# Test dashboard shows stats for logged-in user
def test_dashboard_logged_in(logged_in_user, clean_db, test_app): # Use logged_in_user fixture
    # Add some sessions for this user
    with test_app.app_context():
        user_id = 1 # Assuming first user created by logged_in_user fixture is ID 1
        sess1 = PomodoroSession(user_id=user_id, work_duration=25, break_duration=5)
        sess2 = PomodoroSession(user_id=user_id, work_duration=50, break_duration=10)
        db.session.add_all([sess1, sess2])
        db.session.commit()

    response = logged_in_user.get(url_for('main.dashboard'))
    assert response.status_code == 200
    assert b'Welcome, Test User!' in response.data
    assert b'Total Focused Time:</strong> 75 minutes' in response.data
    assert b'Total Break Time:</strong> 15 minutes' in response.data
    assert b'Completed Pomodoro Sessions:</strong> 2' in response.data

# Test timer page requires login
def test_timer_requires_login(test_client, init_database):
    response = test_client.get(url_for('main.timer'), follow_redirects=True)
    assert response.status_code == 200
    assert b'Login' in response.data # Should redirect to login

# Test timer page loads for logged-in user
def test_timer_page_logged_in(logged_in_user):
    response = logged_in_user.get(url_for('main.timer'))
    assert response.status_code == 200
    assert b'Start a Pomodoro Session' in response.data
    assert b'Work: <input id="work-minutes"' in response.data
    assert b'Break: <input id="break-minutes"' in response.data

# Test completing a session (AJAX endpoint)
def test_complete_session_logged_in(logged_in_user, clean_db, test_app):
    # Clear any existing sessions for the user
    with test_app.app_context():
        from pomodoro_app.models import PomodoroSession
        PomodoroSession.query.delete()
        db.session.commit()
    
    response = logged_in_user.post(url_for('main.complete_session'), json={
        'work': 25,
        'break': 5
    })
    assert response.status_code == 200
    assert response.json == {'status': 'success'}
    
    # Verify that only one session exists
    with test_app.app_context():
        sessions = PomodoroSession.query.all()
        assert len(sessions) == 1
        assert sessions[0].user_id == 1 # Assuming logged_in_user is user ID 1
        assert sessions[0].work_duration == 25
        assert sessions[0].break_duration == 5

# Test complete session requires login
def test_complete_session_requires_login(test_client, init_database):
    response = test_client.post(url_for('main.complete_session'), json={
        'work': 25,
        'break': 5
    })
    # Expecting a 401 Unauthorized or redirect to login depending on Flask-Login setup
    # Since login_view is set, it should redirect
    assert response.status_code == 302 # Redirect status
    assert 'login' in response.location # Check redirect location