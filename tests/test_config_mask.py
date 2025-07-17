import pytest
from config import Config


def test_mask_url_removes_password_query():
    url = 'redis://host/0?password=foo'
    masked = Config._mask_url_credentials(url)
    assert 'password=%2A%2A%2A' in masked
    assert 'foo' not in masked


def test_mask_url_case_insensitive_and_preserves_other_params():
    url = 'redis://host/0?PASS=foo&opt=1'
    masked = Config._mask_url_credentials(url)
    assert 'PASS=%2A%2A%2A' in masked
    assert 'opt=1' in masked
    assert 'foo' not in masked
