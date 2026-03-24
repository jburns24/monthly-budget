# Source: docs/specs/01-spec-project-scaffolding/01-spec-project-scaffolding.md
# Pattern: Web/UI
# Recommended test type: Integration + E2E

Feature: Frontend Scaffolding (React + Vite + Chakra UI)

  Scenario: Placeholder page loads and displays application title
    Given the frontend dev server is running at http://localhost:5173
    When a user navigates to http://localhost:5173/
    Then the page displays the heading "Monthly Budget"
    And the page displays a message confirming the app is running

  Scenario: Placeholder page fetches and displays backend API health status
    Given the frontend dev server is running at http://localhost:5173
    And the backend API server is running and healthy
    When a user navigates to http://localhost:5173/
    Then the page displays the API health status fetched from the backend
    And the displayed status includes "healthy" or a connection indicator

  Scenario: Vite proxies API requests to the backend
    Given the frontend dev server is running at http://localhost:5173
    And the backend API server is running at http://localhost:8000
    When the frontend makes a fetch request to /api/health
    Then the request is proxied to http://localhost:8000/api/health
    And the frontend receives the backend health response without CORS errors

  Scenario: Frontend test suite passes with placeholder test
    Given the frontend project is set up with npm dependencies installed
    When the user runs "cd frontend && npm test"
    Then the command exits with code 0
    And the output shows at least 1 test passed
