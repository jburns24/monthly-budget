# Source: docs/specs/02-spec-authentication/02-spec-authentication.md
# Pattern: Web/UI
# Recommended test type: E2E

Feature: Frontend -- Login Page & Auth Integration

  Scenario: Login page renders with Google Sign-In button
    Given the user is not authenticated
    When the user navigates to /login
    Then the page displays a "Sign in with Google" button
    And the page displays the app logo or name

  Scenario: Clicking Sign-In redirects to Google OAuth with PKCE parameters
    Given the login page is displayed at /login
    When the user clicks the "Sign in with Google" button
    Then the browser redirects to Google's OAuth authorization endpoint
    And the redirect URL includes the "code_challenge" parameter
    And the redirect URL includes "code_challenge_method=S256"
    And the redirect URL includes a "state" parameter
    And the redirect URL includes "scope=openid email profile"
    And the redirect URL includes "response_type=code"

  Scenario: PKCE code_challenge is a correct SHA-256 hash of the code_verifier
    Given a PKCE code_verifier has been generated
    When the code_challenge is computed from the code_verifier
    Then the code_challenge equals the base64url-encoded SHA-256 hash of the code_verifier

  Scenario: OAuth callback route exchanges code and redirects to home
    Given the user has been redirected back from Google with a valid "code" and "state" parameter
    And the "state" parameter matches the value stored in sessionStorage
    And the backend /api/auth/callback returns a successful response with "is_new_user": false
    When the /auth/callback route processes the redirect
    Then the browser navigates to "/"
    And no "?new=true" query parameter is present in the URL

  Scenario: OAuth callback appends new user flag for first-time users
    Given the user has been redirected back from Google with a valid "code" and "state"
    And the backend /api/auth/callback returns a successful response with "is_new_user": true
    When the /auth/callback route processes the redirect
    Then the browser navigates to "/?new=true"

  Scenario: Unauthenticated user is redirected to login page
    Given the user is not authenticated
    And /api/me returns a 401 response
    When the user navigates to /
    Then the browser redirects to /login

  Scenario: Authenticated user can access protected routes
    Given the user is authenticated
    And /api/me returns the user's profile
    When the user navigates to /
    Then the page displays the app content
    And the user is not redirected to /login

  Scenario: Logout clears session and redirects to login
    Given the user is authenticated and viewing the app
    And a logout button is visible in the navigation
    When the user clicks the logout button
    Then a POST request is sent to /api/auth/logout
    And the browser redirects to /login

  Scenario: Silent token refresh on 401 response
    Given the user is authenticated
    And the access token has expired
    When the app makes an API request that returns 401
    Then the app automatically sends a POST request to /api/auth/refresh
    And if the refresh succeeds the original API request is retried

  Scenario: Failed silent refresh redirects to login
    Given the user is authenticated
    And the access token has expired
    And the refresh token is also invalid
    When the app makes an API request that returns 401
    And the subsequent refresh request also returns 401
    Then the browser redirects to /login

  Scenario: OAuth error displays inline error on login page
    Given the login page is displayed at /login
    When the OAuth callback returns an error from Google
    Then an error message is displayed on the login page
    And the "Sign in with Google" button remains available
