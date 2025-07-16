import pytest
from pomodoro_app import create_app, db
from pomodoro_app.models import User
from tests.conftest import TestConfig


class CsrfTimerConfig(TestConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture
def csrf_timer_app():
    app = create_app('testing')
    app.config.from_object(CsrfTimerConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def csrf_timer_client(csrf_timer_app):
    return csrf_timer_app.test_client()


@pytest.fixture
def csrf_logged_in_user(csrf_timer_app, csrf_timer_client):
    from werkzeug.security import generate_password_hash

    hashed_pw = generate_password_hash('testpassword', method='pbkdf2:sha256')
    user = User(email='csrf@example.com', name='CSRF Timer User', password=hashed_pw)
    with csrf_timer_app.app_context():
        db.session.add(user)
        db.session.commit()

    csrf_timer_client.post('/auth/login', data={'email': 'csrf@example.com', 'password': 'testpassword'}, follow_redirects=True)
    yield csrf_timer_client
    csrf_timer_client.get('/auth/logout', follow_redirects=True)
    with csrf_timer_app.app_context():
        db.session.delete(user)
        db.session.commit()


def test_timer_start_requires_csrf(csrf_logged_in_user):
    payload = {'work': 25, 'break': 5}
    resp = csrf_logged_in_user.post('/api/timer/start', json=payload)
    assert resp.status_code == 400
