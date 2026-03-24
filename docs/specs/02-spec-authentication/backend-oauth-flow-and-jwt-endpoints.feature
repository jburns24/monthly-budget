# Source: docs/specs/02-spec-authentication/02-spec-authentication.md
# Pattern: API
# Recommended test type: Integration

Feature: Backend -- OAuth Flow & JWT Endpoints

  Scenario: OAuth callback exchanges code for tokens and sets cookies
    Given the API server is running
    And Google token exchange is mocked to return a valid id_token for "user@example.com"
    When a POST request is sent to /api/auth/callback with body {"code": "auth_code", "code_verifier": "valid_verifier"}
    Then the response status is 200
    And the response sets an "access_token" HttpOnly cookie
    And the response sets a "refresh_token" HttpOnly cookie
    And the response body contains "is_new_user"

  Scenario: OAuth callback creates a new user on first login
    Given the API server is running
    And no user with google_id "g456" exists in the database
    And Google token exchange is mocked to return an id_token with google_id "g456" and email "new@example.com"
    When a POST request is sent to /api/auth/callback with body {"code": "auth_code", "code_verifier": "valid_verifier"}
    Then the response status is 200
    And the response body contains "is_new_user": true
    And a user record exists in the database with google_id "g456" and email "new@example.com"

  Scenario: OAuth callback updates existing user on subsequent login
    Given the API server is running
    And a user with google_id "g456" already exists with display_name "Old Name"
    And Google token exchange is mocked to return an id_token with google_id "g456" and display_name "New Name"
    When a POST request is sent to /api/auth/callback with body {"code": "auth_code", "code_verifier": "valid_verifier"}
    Then the response status is 200
    And the response body contains "is_new_user": false
    And the user's display_name in the database is "New Name"
    And the user's last_login_at has been updated

  Scenario: Refresh endpoint issues new access token with valid refresh cookie
    Given the API server is running
    And a valid refresh token cookie is present for user "user@example.com"
    When a POST request is sent to /api/auth/refresh
    Then the response status is 200
    And the response sets a new "access_token" HttpOnly cookie

  Scenario: Refresh endpoint rejects blacklisted refresh token
    Given the API server is running
    And a refresh token cookie is present whose jti has been blacklisted
    When a POST request is sent to /api/auth/refresh
    Then the response status is 401
    And no new access_token cookie is set

  Scenario: Logout blacklists refresh token and clears cookies
    Given the API server is running
    And the user is authenticated with valid access and refresh token cookies
    When a POST request is sent to /api/auth/logout
    Then the response status is 200
    And the refresh token's jti is recorded in the refresh_token_blacklist table
    And the "access_token" cookie is cleared
    And the "refresh_token" cookie is cleared

  Scenario: GET /api/me returns user profile with valid access token
    Given the API server is running
    And the user is authenticated with a valid access token cookie for "user@example.com"
    When a GET request is sent to /api/me
    Then the response status is 200
    And the response body contains "email": "user@example.com"
    And the response body contains "id", "display_name", "avatar_url", and "timezone" fields

  Scenario: GET /api/me returns 401 without access token cookie
    Given the API server is running
    And no access token cookie is present
    When a GET request is sent to /api/me
    Then the response status is 401

  Scenario: PUT /api/me updates user profile fields
    Given the API server is running
    And the user is authenticated with a valid access token cookie
    When a PUT request is sent to /api/me with body {"display_name": "Updated Name", "timezone": "America/Chicago"}
    Then the response status is 200
    And the user's display_name in the database is "Updated Name"
    And the user's timezone in the database is "America/Chicago"

  Scenario: Expired access token returns 401
    Given the API server is running
    And the user has an expired access token cookie
    When a GET request is sent to /api/me
    Then the response status is 401

  Scenario: CORS allows credentials from frontend origin
    Given the API server is running
    When an OPTIONS request is sent to /api/me with Origin "http://localhost:5173"
    Then the response includes "Access-Control-Allow-Credentials: true"
    And the response includes "Access-Control-Allow-Origin: http://localhost:5173"

  Scenario: Startup fails when JWT secret is too short in non-development mode
    Given the environment variable ENVIRONMENT is set to "production"
    And the environment variable JWT_SECRET is set to "short"
    When the API server attempts to start
    Then the server fails to start
    And the error output indicates JWT_SECRET must be at least 32 characters
