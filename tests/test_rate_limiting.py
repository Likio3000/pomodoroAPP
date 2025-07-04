import pytest
from flask import url_for

@pytest.mark.parametrize("endpoint,limit,method", [
    # Anonymous endpoints with rate limit set to 5 or 10 per minute.
    ("auth.register", 5, "get"),
    ("auth.login", 5, "get"),
    ("main.index", 10, "get"),
])
def test_rate_limit_anonymous(rate_limit_test_client, init_rl_database, endpoint, limit, method):
    """
    Test that anonymous endpoints enforce rate limiting correctly.
    This test sends the maximum allowed number of requests to the endpoint,
    then verifies that one additional request returns a 429 status code.
    """
    url = url_for(endpoint)
    # Send allowed requests
    for i in range(limit):
        if method.lower() == "get":
            response = rate_limit_test_client.get(url)
        elif method.lower() == "post":
            response = rate_limit_test_client.post(url)
        else:
            pytest.skip("Unsupported HTTP method")
        assert response.status_code in (200, 302), (
            f"Request {i+1} to {endpoint} returned status {response.status_code}, expected success."
        )
    # Next request should exceed the limit and return 429
    if method.lower() == "get":
        response = rate_limit_test_client.get(url)
    else:
        response = rate_limit_test_client.post(url)
    assert response.status_code == 429, (
        f"Expected 429 Too Many Requests for {endpoint} after {limit} requests, got {response.status_code}."
    )


@pytest.mark.parametrize("endpoint,limit,method", [
    # Authenticated endpoints with rate limit set to 10 per minute.
    ("main.api_start_timer", 15, "post"),
    ("main.api_complete_phase", 15, "post"),
    ("main.dashboard", 10, "get"),
])
def test_rate_limit_authenticated(logged_in_user_rate_limit, endpoint, limit, method):
    """
    Test that endpoints requiring authentication enforce rate limiting correctly.
    This test uses an authenticated client fixture (with rate limiting enabled)
    to send the maximum allowed number of requests and asserts that an extra request
    receives a 429 status code.
    """
    url = url_for(endpoint)
    for i in range(limit):
        if method.lower() == "get":
            response = logged_in_user_rate_limit.get(url)
        elif method.lower() == "post":
            if endpoint == "main.api_complete_phase":
                response = logged_in_user_rate_limit.post(url, json={"phase_completed": "work"})
            elif endpoint == "main.api_start_timer":
                response = logged_in_user_rate_limit.post(url, json={"work": 25, "break": 5})
            else:
                response = logged_in_user_rate_limit.post(url)
        else:
            pytest.skip("Unsupported HTTP method")
        assert response.status_code in (200, 302, 400), (
            f"Request {i+1} to authenticated endpoint {endpoint} returned status {response.status_code}, expected success."
        )
    # Next request should be rate limited.
    if method.lower() == "get":
        response = logged_in_user_rate_limit.get(url)
    elif method.lower() == "post":
        if endpoint == "main.api_complete_phase":
            response = logged_in_user_rate_limit.post(url, json={"phase_completed": "work"})
        elif endpoint == "main.api_start_timer":
            response = logged_in_user_rate_limit.post(url, json={"work": 25, "break": 5})
        else:
            response = logged_in_user_rate_limit.post(url)
    assert response.status_code == 429, (
        f"Expected 429 Too Many Requests for authenticated endpoint {endpoint} after {limit} requests, got {response.status_code}."
    )
