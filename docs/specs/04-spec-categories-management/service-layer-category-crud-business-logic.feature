# Source: docs/specs/04-spec-categories-management/04-spec-categories-management.md
# Pattern: API
# Recommended test type: Integration

Feature: Service Layer — Category CRUD Business Logic

  Scenario: Create category returns new category object
    Given a family exists in the database
    When create_category is called with family_id, name "Transport", icon "🚗", sort_order 2
    Then a category object is returned with name "Transport", icon "🚗", sort_order 2, and is_active true

  Scenario: Create category with duplicate name returns 409
    Given a family exists in the database
    And a category named "Groceries" exists for that family
    When create_category is called with the same family_id and name "Groceries"
    Then an HTTPException with status 409 is raised

  Scenario: List active categories returns only active items sorted correctly
    Given a family exists with categories: "Bills" (sort_order 2, active), "Dining" (sort_order 1, active), "Archive" (sort_order 0, inactive)
    When list_active_categories is called for that family
    Then the result contains 2 categories in order: "Dining" (sort_order 1), "Bills" (sort_order 2)
    And "Archive" is not included in the result

  Scenario: Update category changes specified fields only
    Given a family exists with a category named "Food" with icon "🍔" and sort_order 0
    When update_category is called with only name "Groceries" (icon and sort_order are None)
    Then the category name is updated to "Groceries"
    And the icon remains "🍔" and sort_order remains 0

  Scenario: Update category with conflicting name returns 409
    Given a family exists with categories "Groceries" and "Dining"
    When update_category is called to rename "Dining" to "Groceries"
    Then an HTTPException with status 409 is raised

  Scenario: Update non-existent category returns 404
    Given a family exists in the database
    When update_category is called with a non-existent category_id for that family
    Then an HTTPException with status 404 is raised

  Scenario: Delete category with no expenses hard-deletes the row
    Given a family exists with a category "Temporary" that has no expense references
    When delete_category is called for "Temporary"
    Then the response contains deleted true
    And the category no longer exists in the database

  Scenario: Delete category with expenses archives instead of deleting
    Given a family exists with a category "Dining" that has 3 expense references
    When delete_category is called for "Dining"
    Then the response contains deleted false, archived true, and expense_count 3
    And the category still exists in the database with is_active false

  Scenario: Delete non-existent category returns 404
    Given a family exists in the database
    When delete_category is called with a non-existent category_id
    Then an HTTPException with status 404 is raised

  Scenario: Seed default categories creates all 6 defaults
    Given a family exists with no categories
    When seed_default_categories is called for that family
    Then 6 categories are created: Groceries, Dining, Transport, Entertainment, Bills, Other
    And each category has an emoji icon and sequential sort_order values

  Scenario: Seed default categories is idempotent
    Given a family exists that already has the 6 default categories
    When seed_default_categories is called again for that family
    Then no new categories are created
    And the existing 6 categories remain unchanged
