# tests/test_main.py
from flask import url_for
import json
from pomodoro_app.main import api_routes
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
    assert b'Points Today:</strong> 0' in response.data
    assert b'Points This Week:</strong> 0' in response.data

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


def test_api_chat_uses_configured_prompt(logged_in_user, test_app, tmp_path, monkeypatch):
    persona_file = tmp_path / "personas.json"
    persona_file.write_text(json.dumps({
        "testagent": {"prompt": "Special persona for tests.", "voice": "alloy"},
        "default": {"prompt": "Default persona", "voice": "all"}
    }))
    with test_app.app_context():
        test_app.config["FEATURE_CHAT_ENABLED"] = True
        test_app.config["AGENT_PERSONA_FILE"] = str(persona_file)

    recorded = {}

    class DummyCompletion:
        @staticmethod
        def create(messages, model=None, max_tokens=None, temperature=None, user=None):
            recorded["messages"] = messages
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "hi"})()})]})()

    class DummyChat:
        completions = DummyCompletion()

    class DummySpeech:
        @staticmethod
        def create(*args, **kwargs):
            class DummyResp:
                def stream_to_file(self, path):
                    pass
            return DummyResp()

    class DummyAudio:
        speech = DummySpeech()

    class DummyOpenAI:
        chat = DummyChat()
        audio = DummyAudio()

    monkeypatch.setattr(api_routes, "openai_client", DummyOpenAI)
    monkeypatch.setattr(api_routes, "_openai_initialized", True)

    resp = logged_in_user.post(url_for('main.api_chat'), json={
        'prompt': 'Hi',
        'dashboard_data': {},
        'tts_enabled': False,
        'agent_type': 'testagent'
    })
    assert resp.status_code == 200
    assert recorded["messages"][0]["content"].lstrip().startswith("Special persona for tests.")


def test_mydata_requires_login(test_client, init_database):
    resp = test_client.get(url_for('main.my_data'), follow_redirects=True)
    assert resp.status_code == 200
    assert b'Login' in resp.data


def test_mydata_view_has_pair_delete_only(logged_in_user, clean_db, test_app):
    from pomodoro_app.models import ChatMessage, User

    with test_app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        msg1 = ChatMessage(user_id=user.id, role='user', text='hello')
        msg2 = ChatMessage(user_id=user.id, role='assistant', text='hi')
        db.session.add_all([msg1, msg2])
        db.session.commit()

    resp = logged_in_user.get(url_for('main.my_data'))
    assert resp.status_code == 200
    assert b'hello' in resp.data
    assert b'Delete Pair' in resp.data
    assert b'btn-danger' not in resp.data


def test_mydata_delete_pair(logged_in_user, clean_db, test_app):
    from pomodoro_app.models import ChatMessage, User

    with test_app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        m1 = ChatMessage(user_id=user.id, role='user', text='q1')
        m2 = ChatMessage(user_id=user.id, role='assistant', text='a1')
        m3 = ChatMessage(user_id=user.id, role='user', text='q2')
        m4 = ChatMessage(user_id=user.id, role='assistant', text='a2')
        db.session.add_all([m1, m2, m3, m4])
        db.session.commit()
        pair_start_id = m1.id

    resp = logged_in_user.post(
        url_for('main.delete_message_pair', message_id=pair_start_id),
        follow_redirects=True
    )
    assert resp.status_code == 200
    assert b'Message pair deleted' in resp.data

    with test_app.app_context():
        assert ChatMessage.query.get(pair_start_id) is None
        assert ChatMessage.query.filter_by(role='assistant', text='a1').first() is None
        # Ensure later messages remain
        assert ChatMessage.query.filter_by(role='user', text='q2').first() is not None


def test_mydata_limit(logged_in_user, clean_db, test_app, monkeypatch):
    from pomodoro_app.main import api_routes

    class DummyCompletion:
        @staticmethod
        def create(messages, model=None, max_tokens=None, temperature=None, user=None):
            return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "ok"})()})]})()

    class DummyChat:
        completions = DummyCompletion()

    class DummySpeech:
        @staticmethod
        def create(*args, **kwargs):
            class DummyResp:
                def stream_to_file(self, path):
                    pass
            return DummyResp()

    class DummyAudio:
        speech = DummySpeech()

    class DummyOpenAI:
        chat = DummyChat()
        audio = DummyAudio()

    monkeypatch.setattr(api_routes, "openai_client", DummyOpenAI)
    monkeypatch.setattr(api_routes, "_openai_initialized", True)

    for i in range(10):
        resp = logged_in_user.post(url_for('main.api_chat'), json={
            'prompt': f'msg {i}',
            'dashboard_data': {},
            'tts_enabled': False
        })
        assert resp.status_code == 200

    resp = logged_in_user.get(url_for('main.my_data'))
    assert resp.status_code == 200
    assert resp.data.count(b'chat-history-item') == 15

    with test_app.app_context():
        from pomodoro_app.models import ChatMessage, User
        user = User.query.filter_by(email='test@example.com').first()
        assert ChatMessage.query.filter_by(user_id=user.id).count() == 15


def test_settings_page_requires_login(test_client, init_database):
    resp = test_client.get(url_for('main.settings'), follow_redirects=True)
    assert resp.status_code == 200
    assert b'Login' in resp.data


def test_update_settings(logged_in_user, test_app):
    resp = logged_in_user.post(url_for('main.settings'), data={
        'preferred_work_minutes': '30',
        'productivity_goal': 'Write more code',
        'submit': True
    }, follow_redirects=True)
    assert resp.status_code == 200
    with test_app.app_context():
        from pomodoro_app.models import User
        user = User.query.filter_by(email='test@example.com').first()
        assert user.preferred_work_minutes == 30
        assert user.productivity_goal == 'Write more code'
