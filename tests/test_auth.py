# tests/test_auth.py
from flask import url_for

# Test registration page
def test_register_page(test_client, init_database):
    response = test_client.get(url_for('auth.register'))
    assert response.status_code == 200
    assert b'Create an Account' in response.data
    assert b'Email' in response.data
    assert b'Password' in response.data

# Test successful registration
def test_successful_registration(test_client, init_database):
    response = test_client.post(url_for('auth.register'), data=dict(
        name='New User',
        email='new@example.com',
        password='password123',
        confirm='password123'
    ), follow_redirects=True) # follow_redirects=True to follow the redirect to login
    assert response.status_code == 200
    assert b'Account created successfully!' in response.data # Check flash message
    assert b'Login' in response.data # Should be redirected to login page

# Test registration with existing email
def test_register_existing_email(test_client, init_database):
    # First, register a user
    test_client.post(url_for('auth.register'), data=dict(
        name='Existing User',
        email='exists@example.com',
        password='password123',
        confirm='password123'
    ), follow_redirects=True)
    # Now, try to register again with the same email
    response = test_client.post(url_for('auth.register'), data=dict(
        name='Another User',
        email='exists@example.com',
        password='password456',
        confirm='password456'
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'Email is already registered.' in response.data # Check flash message
    assert b'Create an Account' in response.data # Should stay on registration page

# Test successful login
def test_successful_login(test_client, init_database):
    # Register user first
    test_client.post(url_for('auth.register'), data=dict(
        name='Login User',
        email='login@example.com',
        password='password123',
        confirm='password123'
    ), follow_redirects=True)
    # Attempt login
    response = test_client.post(url_for('auth.login'), data=dict(
        email='login@example.com',
        password='password123'
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data # Should redirect to dashboard
    assert b'Welcome, Login User!' in response.data # Check welcome message

# Test login with incorrect password
def test_login_incorrect_password(test_client, init_database):
     # Register user first
    test_client.post(url_for('auth.register'), data=dict(
        name='Login User BadPass',
        email='badpass@example.com',
        password='password123',
        confirm='password123'
    ), follow_redirects=True)
    # Attempt login with wrong password
    response = test_client.post(url_for('auth.login'), data=dict(
        email='badpass@example.com',
        password='wrongpassword'
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid email or password. Please try again.' in response.data
    assert b'Login' in response.data # Stay on login page

# Test logout
def test_logout(logged_in_user): # Use the logged_in_user fixture
    response = logged_in_user.get(url_for('auth.logout'), follow_redirects=True)
    assert response.status_code == 200
    assert b'You have been logged out.' in response.data
    assert b'Login' in response.data # Should redirect to login