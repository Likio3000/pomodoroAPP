import os
import pytest
from pomodoro_app import create_app
from config import DevelopmentConfig


def test_production_raises_on_default_secret(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', DevelopmentConfig.SECRET_KEY)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///dummy.db')
    monkeypatch.setenv('REDIS_URL', 'redis://localhost:6379/0')
    with pytest.raises(SystemExit):
        create_app('production')
