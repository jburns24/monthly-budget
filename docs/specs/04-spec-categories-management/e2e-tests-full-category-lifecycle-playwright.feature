# Source: docs/specs/04-spec-categories-management/04-spec-categories-management.md
# Pattern: Web/UI
# Recommended test type: E2E

Feature: E2E Tests — Full Category Lifecycle via Playwright

  Scenario: Admin creates a category and sees it in the list
    Given test data is reset and the user is authenticated as a family admin
    And a family has been created via the API
    When the admin navigates to /categories
    And clicks "Add Category" and enters name "Groceries" with icon "🛒"
    And submits the form
    Then "Groceries" with icon "🛒" appears in the category list

  Scenario: Admin edits a category name and sees the update
    Given test data is reset and the user is authenticated as a family admin
    And a category named "Food" exists in the family
    When the admin clicks the edit button on "Food"
    And changes the name to "Groceries" and saves
    Then the category list shows "Groceries" instead of "Food"

  Scenario: Admin deletes a category with no expenses
    Given test data is reset and the user is authenticated as a family admin
    And a category named "Temporary" exists in the family
    When the admin clicks the delete button on "Temporary"
    And confirms the deletion
    Then "Temporary" is no longer visible in the category list

  Scenario: Seed defaults creates 6 categories
    Given test data is reset and the user is authenticated as a family admin
    And the family has no categories
    When the admin navigates to /categories
    And clicks the "Seed default categories" button
    Then 6 categories appear in the list: Groceries, Dining, Transport, Entertainment, Bills, Other

  Scenario: Member can view categories but cannot see admin actions
    Given test data is reset and a family exists with 3 categories
    And the user is authenticated as a non-admin member of that family
    When the member navigates to /categories
    Then the 3 categories are displayed in the list
    And no "Add Category" button is visible
    And no edit or delete buttons are visible on any category row
