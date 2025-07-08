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
    assert b'Pomodoro Session' in response.data
    assert b'Work: <input id="work-minutes"' in response.data
    assert b'Break: <input id="break-minutes"' in response.data

# Test completing a session (AJAX endpoint)
def test_complete_session_logged_in(logged_in_user, clean_db, test_app):
    # Clear any existing sessions for the user
    with test_app.app_context():
        from pomodoro_app.models import PomodoroSession
        PomodoroSession.query.delete()
        db.session.commit()
    
    # Start a timer so the API has state to work with
    start_resp = logged_in_user.post(url_for('main.api_start_timer'), json={
        'work': 25,
        'break': 5
    })
    assert start_resp.status_code == 200

    # Fast-forward the timer by setting the end_time in the past
    from datetime import datetime, timedelta, timezone
    with test_app.app_context():
        from pomodoro_app.models import ActiveTimerState
        state = ActiveTimerState.query.filter_by(user_id=1).first()
        state.end_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()

    response = logged_in_user.post(url_for('main.api_complete_phase'), json={
        'phase_completed': 'work'
    })
    assert response.status_code == 200
    assert response.json['status'] == 'break_started'
    assert 'total_points' in response.json
    assert 'end_time' in response.json

    # Verify that one session was logged
    with test_app.app_context():
        sessions = PomodoroSession.query.all()
        assert len(sessions) == 1
        assert sessions[0].user_id == 1
        assert sessions[0].work_duration == 25
        assert sessions[0].break_duration == 5

# Test complete session requires login
def test_complete_session_requires_login(test_client, init_database):
    response = test_client.post(url_for('main.api_complete_phase'), json={
        'phase_completed': 'work'
    })
    # Expecting a 401 Unauthorized or redirect to login depending on Flask-Login setup
    # Since login_view is set, it should redirect
    assert response.status_code == 302 # Redirect status
    assert 'login' in response.location # Check redirect location


def test_leaderboard_page(test_client, init_database, test_app):
    from werkzeug.security import generate_password_hash
    with test_app.app_context():
        from pomodoro_app.models import User
        user1 = User(name='Alice', email='alice@example.com', password=generate_password_hash('a'), total_points=100)
        user2 = User(name='Bob', email='bob@example.com', password=generate_password_hash('b'), total_points=50)
        db.session.add_all([user1, user2])
        db.session.commit()

    response = test_client.get(url_for('main.leaderboard'))
    assert response.status_code == 200
    assert b'Leaderboard' in response.data
    assert b'Alice' in response.data
