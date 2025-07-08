import pytest
from flask import url_for
from types import SimpleNamespace
from unittest.mock import MagicMock

from pomodoro_app import create_app, db, limiter
from pomodoro_app.models import User
from tests.conftest import TestConfig, RateLimitTestConfig


class ChatTestConfig(TestConfig):
    FEATURE_CHAT_ENABLED = True
    OPENAI_API_KEY = 'test-key'
    TTS_ENABLED = True


@pytest.fixture
def chat_app():
    app = create_app('testing')
    app.config.from_object(ChatTestConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def chat_client(chat_app):
    return chat_app.test_client()


@pytest.fixture
def chat_logged_in_user(chat_app, chat_client):
    from werkzeug.security import generate_password_hash

    hashed_pw = generate_password_hash('testpassword', method='pbkdf2:sha256')
    user = User(email='chat@example.com', name='Chat User', password=hashed_pw)
    with chat_app.app_context():
        db.session.add(user)
        db.session.commit()

    chat_client.post('/auth/login', data={'email': 'chat@example.com', 'password': 'testpassword'}, follow_redirects=True)
    yield chat_client
    chat_client.get('/auth/logout', follow_redirects=True)
    with chat_app.app_context():
        db.session.delete(user)
        db.session.commit()


@pytest.fixture
def mock_openai(monkeypatch):
    from pomodoro_app.main import api_routes

    chat_create = MagicMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='mock response'))]
    ))

    class DummyTTSResponse:
        def stream_to_file(self, path):
            with open(path, 'wb') as f:
                f.write(b'voice')

    tts_create = MagicMock(return_value=DummyTTSResponse())

    mock_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        audio=SimpleNamespace(speech=SimpleNamespace(create=tts_create))
    )

    monkeypatch.setattr(api_routes, 'openai_client', mock_client)
    monkeypatch.setattr(api_routes, '_openai_initialized', True)
    return chat_create, tts_create


def test_chat_valid_prompt(chat_logged_in_user, chat_app, mock_openai):
    chat_create, tts_create = mock_openai
    chat_app.config['TTS_ENABLED'] = True
    payload = {'prompt': 'Hello', 'dashboard_data': {}, 'tts_enabled': False}
    resp = chat_logged_in_user.post('/api/chat', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['response'] == 'mock response'
    assert data['audio_url'] is None
    chat_create.assert_called_once()
    tts_create.assert_not_called()


def test_chat_missing_params(chat_logged_in_user, mock_openai):
    payload = {'prompt': 'Hello'}
    resp = chat_logged_in_user.post('/api/chat', json=payload)
    assert resp.status_code == 400


def test_chat_tts_enabled(chat_logged_in_user, chat_app, mock_openai):
    chat_create, tts_create = mock_openai
    chat_app.config['TTS_ENABLED'] = True
    payload = {'prompt': 'Hi', 'dashboard_data': {}, 'tts_enabled': True}
    resp = chat_logged_in_user.post('/api/chat', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['audio_url']
    chat_create.assert_called_once()
    tts_create.assert_called_once()


def test_chat_server_tts_disabled(chat_logged_in_user, chat_app, mock_openai):
    chat_create, tts_create = mock_openai
    chat_app.config['TTS_ENABLED'] = False
    payload = {'prompt': 'Hi', 'dashboard_data': {}, 'tts_enabled': True}
    resp = chat_logged_in_user.post('/api/chat', json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['audio_url'] is None
    tts_create.assert_not_called()


class CsrfChatConfig(ChatTestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def csrf_chat_app():
    app = create_app('testing')
    app.config.from_object(CsrfChatConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def csrf_client(csrf_chat_app):
    return csrf_chat_app.test_client()


@pytest.fixture
def csrf_logged_in_user(csrf_chat_app, csrf_client):
    from werkzeug.security import generate_password_hash

    hashed_pw = generate_password_hash('testpassword', method='pbkdf2:sha256')
    user = User(email='csrf@example.com', name='CSRF User', password=hashed_pw)
    with csrf_chat_app.app_context():
        db.session.add(user)
        db.session.commit()

    csrf_client.post('/auth/login', data={'email': 'csrf@example.com', 'password': 'testpassword'}, follow_redirects=True)
    yield csrf_client
    csrf_client.get('/auth/logout', follow_redirects=True)
    with csrf_chat_app.app_context():
        db.session.delete(user)
        db.session.commit()


def test_chat_csrf_enforced(csrf_logged_in_user, mock_openai):
    payload = {'prompt': 'Hi', 'dashboard_data': {}, 'tts_enabled': False}
    resp = csrf_logged_in_user.post('/api/chat', json=payload)
    assert resp.status_code == 400


class ChatRateLimitConfig(RateLimitTestConfig):
    FEATURE_CHAT_ENABLED = True
    OPENAI_API_KEY = 'test-key'
    TTS_ENABLED = False


@pytest.fixture
def chat_rate_limit_app():
    limiter.enabled = True
    app = create_app('development')
    app.config.from_object(ChatRateLimitConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()
    limiter.enabled = False


@pytest.fixture
def chat_rate_limit_client(chat_rate_limit_app):
    return chat_rate_limit_app.test_client()


@pytest.fixture
def logged_in_user_chat_rate_limit(chat_rate_limit_app, chat_rate_limit_client):
    from werkzeug.security import generate_password_hash

    hashed_pw = generate_password_hash('testpassword', method='pbkdf2:sha256')
    user = User(email='rate@example.com', name='Rate User', password=hashed_pw)
    with chat_rate_limit_app.app_context():
        db.session.add(user)
        db.session.commit()

    chat_rate_limit_client.post('/auth/login', data={'email': 'rate@example.com', 'password': 'testpassword'}, follow_redirects=False)
    yield chat_rate_limit_client
    chat_rate_limit_client.get('/auth/logout', follow_redirects=True)
    with chat_rate_limit_app.app_context():
        db.session.delete(user)
        db.session.commit()


def test_chat_rate_limiting(logged_in_user_chat_rate_limit, mock_openai):
    payload = {'prompt': 'Hi', 'dashboard_data': {}, 'tts_enabled': False}
    url = '/api/chat'
    for _ in range(10):
        r = logged_in_user_chat_rate_limit.post(url, json=payload)
        assert r.status_code == 200
    r = logged_in_user_chat_rate_limit.post(url, json=payload)
    assert r.status_code == 429

