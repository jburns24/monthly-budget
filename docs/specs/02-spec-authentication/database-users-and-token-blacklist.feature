# Source: docs/specs/02-spec-authentication/02-spec-authentication.md
# Pattern: State Persistence + API
# Recommended test type: Integration

Feature: Database -- Users & Token Blacklist

  Scenario: Users table is created with all required columns via migration
    Given the database has no "users" table
    When Alembic migrations are run with "alembic upgrade head"
    Then the "users" table exists in the database
    And it contains columns "id", "google_id", "email", "display_name", "avatar_url", "timezone", "created_at", "last_login_at"
    And the "google_id" column has a UNIQUE constraint
    And the "email" column has a UNIQUE constraint
    And the "timezone" column defaults to "America/New_York"

  Scenario: Refresh token blacklist table is created with indexes via migration
    Given the database has no "refresh_token_blacklist" table
    When Alembic migrations are run with "alembic upgrade head"
    Then the "refresh_token_blacklist" table exists in the database
    And it contains columns "id", "jti", "user_id", "expires_at", "created_at"
    And the "jti" column has a UNIQUE constraint
    And an index exists on the "jti" column
    And an index exists on the "expires_at" column
    And the "user_id" column has a foreign key to "users.id" with ON DELETE CASCADE

  Scenario: Migration is reversible
    Given the database has been migrated to the latest revision
    When "alembic downgrade -1" is executed
    Then the "users" table no longer exists
    And the "refresh_token_blacklist" table no longer exists
    And no errors are raised during downgrade

  Scenario: User ORM model maps correctly to the schema
    Given the database has been migrated to the latest revision
    When a User record is created with google_id "g123", email "test@example.com", and display_name "Test User"
    And the record is committed and re-queried from the database
    Then the returned User has google_id "g123", email "test@example.com", and display_name "Test User"
    And "created_at" is automatically populated with a timestamp
    And "timezone" is "America/New_York"

  Scenario: RefreshTokenBlacklist ORM model maps correctly to the schema
    Given a User record exists in the database
    When a RefreshTokenBlacklist record is created with a jti, the user's id, and an expires_at timestamp
    And the record is committed and re-queried from the database
    Then the returned record has the correct jti, user_id, and expires_at values
    And "created_at" is automatically populated with a timestamp
