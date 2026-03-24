# Source: docs/specs/01-spec-project-scaffolding/01-spec-project-scaffolding.md
# Pattern: CLI/Process + State
# Recommended test type: Integration

Feature: Docker Compose and Infrastructure

  Scenario: All four services start successfully with docker compose up
    Given the project root contains a docker-compose.yml
    And .env files are configured with valid local development values
    When the user runs "docker compose up -d" from the project root
    Then all four services (api, db, redis, frontend) are listed in "docker compose ps" output
    And no service shows a status of "exited" or "restarting"

  Scenario: All services pass health checks
    Given all four services have been started with "docker compose up -d"
    When the user runs "docker compose ps"
    Then the api service shows status "healthy"
    And the db service shows status "healthy"
    And the redis service shows status "healthy"

  Scenario: API service waits for healthy database and redis before starting
    Given the docker-compose.yml defines api depends_on db and redis with condition service_healthy
    When the user runs "docker compose up -d"
    And the db and redis services become healthy
    Then the api service starts after db and redis are healthy
    And the api service runs Alembic migrations before accepting requests

  Scenario: PostgreSQL data persists across restarts
    Given all services are running via docker compose
    And the PostgreSQL database contains the initial migration state
    When the user runs "docker compose down"
    And the user runs "docker compose up -d"
    And all services become healthy
    Then the PostgreSQL database still contains the previous migration state
    And the pg_data volume was not removed

  Scenario: Redis requires password authentication
    Given all services are running via docker compose
    When a client attempts to connect to Redis without a password
    Then the Redis connection is rejected with an authentication error
    And a client connecting with the correct password from the environment succeeds

  Scenario: API container runs with security hardening
    Given the api service is running via docker compose
    When the user inspects the api container configuration
    Then the container filesystem is read-only
    And the container has security_opt no-new-privileges set
    And the container has all capabilities dropped
