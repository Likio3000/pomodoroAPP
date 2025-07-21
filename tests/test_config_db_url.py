import os
import subprocess
import sys


def get_database_uri(config_name, url):
    env = os.environ.copy()
    env['DATABASE_URL'] = url
    env.setdefault('REDIS_URL', 'redis://localhost:6379/0')
    # Avoid setting SECRET_KEY in the environment so DevelopmentConfig
    # keeps its default value. Instead set it inside the Python command
    # prior to creating the app.
    code = (
        "import pomodoro_app, os, json;"
        "os.environ['SECRET_KEY']='test-config-secret';"
        f"app=pomodoro_app.create_app('{config_name}');"
        "print(app.config['SQLALCHEMY_DATABASE_URI'])"
    )
    result = subprocess.check_output([sys.executable, '-c', code], env=env, text=True)
    # Last line should contain the URI
    return result.strip().splitlines()[-1]


def test_postgres_scheme_normalized():
    uri = get_database_uri('development', 'postgres://u:p@localhost/db')
    assert uri == 'postgresql://u:p@localhost/db'


def test_postgres_scheme_normalized_production():
    uri = get_database_uri('production', 'postgres://u:p@localhost/db')
    assert uri == 'postgresql://u:p@localhost/db'


def test_postgresql_scheme_unchanged():
    uri = get_database_uri('development', 'postgresql://u:p@localhost/db')
    assert uri == 'postgresql://u:p@localhost/db'
