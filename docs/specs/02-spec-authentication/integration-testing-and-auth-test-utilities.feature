# Source: docs/specs/02-spec-authentication/02-spec-authentication.md
# Pattern: API + State
# Recommended test type: Integration

Feature: Integration Testing & Auth Test Utilities

  Scenario: create_test_user factory produces a valid user in the test database
    Given the test database is running with migrations applied
    When the create_test_user factory function is called with default parameters
    Then a User record is persisted in the test database
    And the returned User object has a valid UUID id, email, google_id, and display_name

  Scenario: authenticated_client fixture provides a client with valid JWT cookies
    Given the test database is running with migrations applied
    And a test user has been created
    When a test function uses the authenticated_client fixture
    And sends a GET request to /api/me
    Then the response status is 200
    And the response body contains the test user's email

  Scenario: mock_google_oauth fixture intercepts Google token exchange
    Given the test database is running with migrations applied
    And the mock_google_oauth fixture is active with a configured id_token for "mock@example.com"
    When a POST request is sent to /api/auth/callback with a code and code_verifier
    Then the response status is 200
    And the user record in the database has email "mock@example.com"
    And no actual HTTP request is made to Google's token endpoint

  Scenario: Full auth flow integration test passes end-to-end
    Given the test database is running with migrations applied
    And Google token exchange is mocked
    When the OAuth callback endpoint is called with valid parameters
    And the returned cookies are used to call GET /api/me
    And a refresh request is sent to /api/auth/refresh
    And a logout request is sent to /api/auth/logout
    And GET /api/me is called again with the original cookies
    Then the initial /api/me call returns 200 with user data
    And the refresh call returns 200 with a new access token cookie
    And the logout call returns 200 and clears cookies
    And the final /api/me call returns 401

  Scenario: Frontend auth redirect flow works with mocked API responses
    Given the React app is rendered in a test environment
    And API responses are mocked so that /api/me returns 401
    When the app loads
    Then the user is redirected to the /login route
    And the "Sign in with Google" button is visible

  Scenario: All auth tests pass via task runner
    Given the backend and frontend test suites are configured
    When "task test" is executed
    Then all auth-related backend tests pass
    And all auth-related frontend tests pass
    And the exit code is 0
