# Source: docs/specs/04-spec-categories-management/04-spec-categories-management.md
# Pattern: State + API
# Recommended test type: Integration

Feature: Database — Categories Table, Model & Migration

  Scenario: Migration creates categories table and can be reversed
    Given the database has all prior migrations applied
    When the categories migration is applied via Alembic upgrade
    Then the "categories" table exists with columns: id (UUID), family_id (UUID), name (VARCHAR 100), icon (VARCHAR 50), sort_order (INTEGER), is_active (BOOLEAN), created_at (TIMESTAMPTZ)
    And the unique constraint on (family_id, name) is present
    And the index "idx_categories_family" exists on the family_id column
    When the migration is rolled back via Alembic downgrade
    Then the "categories" table no longer exists

  Scenario: Category can be created and retrieved with all fields
    Given a family exists in the database
    When a category is inserted with name "Groceries", icon "🛒", sort_order 1, and is_active true for that family
    Then the category can be retrieved by its UUID primary key
    And the retrieved category has name "Groceries", icon "🛒", sort_order 1, is_active true, and a non-null created_at timestamp

  Scenario: Duplicate category name within a family raises integrity error
    Given a family exists in the database
    And a category named "Dining" exists for that family
    When a second category named "Dining" is inserted for the same family
    Then an IntegrityError is raised due to the unique constraint violation

  Scenario: Category defaults are applied correctly
    Given a family exists in the database
    When a category is inserted with only name "Bills" and family_id (no sort_order or is_active specified)
    Then the category has is_active defaulting to true
    And the category has sort_order defaulting to 0

  Scenario: Deleting a family cascades to its categories
    Given a family exists in the database
    And that family has 3 categories
    When the family row is deleted from the database
    Then all 3 categories belonging to that family are also deleted
