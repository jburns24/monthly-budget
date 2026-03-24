# Source: docs/specs/01-spec-project-scaffolding/01-spec-project-scaffolding.md
# Pattern: CLI/Process
# Recommended test type: Integration

Feature: Pre-commit, CI Pipeline and Developer Tooling

  Scenario: Pre-commit runs all code quality checks successfully
    Given the project codebase has all dependencies installed
    And pre-commit is installed via "pre-commit install"
    When the user runs "pre-commit run --all-files"
    Then the command exits with code 0
    And the output shows ruff check passed for backend Python files
    And the output shows ruff format check passed for backend Python files
    And the output shows eslint passed for frontend files
    And the output shows prettier check passed for frontend files
    And the output shows type checking passed for both backend and frontend

  Scenario: Pre-commit hooks run automatically on git commit
    Given pre-commit hooks are installed via "pre-commit install"
    And the developer has staged a file for commit
    When the developer runs "git commit"
    Then pre-commit hooks execute before the commit is finalized
    And if all hooks pass the commit proceeds

  Scenario: Make lint runs pre-commit checks
    Given the project root contains a Makefile with a lint target
    When the user runs "make lint"
    Then the command executes "pre-commit run --all-files"
    And the command exits with code 0

  Scenario: Make test runs both backend and frontend test suites
    Given the project root contains a Makefile with a test target
    And all dependencies are installed
    When the user runs "make test"
    Then backend pytest tests are executed and pass
    And frontend vitest tests are executed and pass
    And the command exits with code 0

  Scenario: Make up starts the full Docker Compose stack
    Given the project root contains a Makefile with an up target
    When the user runs "make up"
    Then docker compose services are started
    And all services eventually reach healthy status

  Scenario: Backend env example contains all required secret placeholders
    Given the file backend/.env.example exists
    When the user reads backend/.env.example
    Then the file contains placeholder entries for DATABASE_URL
    And the file contains placeholder entries for REDIS_URL
    And the file contains placeholder entries for JWT_SECRET
    And the file contains placeholder entries for GOOGLE_CLIENT_ID
    And the file contains placeholder entries for GOOGLE_CLIENT_SECRET
    And the file contains placeholder entries for ANTHROPIC_API_KEY

  Scenario: CI pipeline runs pre-commit and tests on pull request
    Given a pull request is opened against the main branch
    And the GitHub Actions workflow .github/workflows/ci.yml is configured
    When the CI pipeline is triggered
    Then the pipeline runs "pre-commit run --all-files" as a step
    And the pipeline runs backend pytest against a PostgreSQL service container
    And the pipeline runs frontend vitest
    And the pipeline reports overall pass or fail status

  Scenario: Detect-secrets hook prevents committing secrets
    Given pre-commit is configured with the detect-secrets hook
    And a file containing a string matching a secret pattern is staged
    When the developer runs "pre-commit run detect-secrets"
    Then the hook flags the potential secret
    And the command exits with a non-zero code
