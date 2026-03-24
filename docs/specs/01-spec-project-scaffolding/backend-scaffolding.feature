# Source: docs/specs/01-spec-project-scaffolding/01-spec-project-scaffolding.md
# Pattern: API + CLI/Process
# Recommended test type: Integration

Feature: Backend Scaffolding (FastAPI + uv + Alembic)

  Scenario: Health endpoint reports healthy status when all dependencies are reachable
    Given the backend API server is running with PostgreSQL and Redis available
    When a GET request is sent to /api/health
    Then the response status is 200
    And the response body contains "status": "healthy"
    And the response body contains "database": "connected"
    And the response body contains "redis": "connected"

  Scenario: Health endpoint reports degraded status when a dependency is unreachable
    Given the backend API server is running
    And the Redis service is stopped
    When a GET request is sent to /api/health
    Then the response status is 503
    And the response body indicates Redis is not connected

  Scenario: Readiness endpoint returns 200 when migrations are current
    Given the backend API server is running with all migrations applied
    When a GET request is sent to /api/health/ready
    Then the response status is 200

  Scenario: Prometheus metrics endpoint returns instrumentation data
    Given the backend API server is running
    And at least one request has been made to /api/health
    When a GET request is sent to /metrics
    Then the response status is 200
    And the response body contains Prometheus-formatted text with metric names and values

  Scenario: Alembic migration tooling is configured and current
    Given the backend project is set up with uv dependencies installed
    When the user runs "cd backend && uv run alembic current" from the project root
    Then the command exits with code 0
    And the output shows the initial migration revision as head

  Scenario: Backend test suite passes with placeholder test
    Given the backend project is set up with uv dependencies installed
    When the user runs "cd backend && uv run pytest"
    Then the command exits with code 0
    And the output shows at least 1 test passed

  Scenario: Structured JSON logging is active in production mode
    Given the backend API server is running with the environment variable LOG_FORMAT set to "json"
    When a GET request is sent to /api/health
    Then the application log output contains valid JSON log entries
    And each log entry includes a timestamp and log level field
