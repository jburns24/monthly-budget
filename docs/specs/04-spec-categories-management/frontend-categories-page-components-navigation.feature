# Source: docs/specs/04-spec-categories-management/04-spec-categories-management.md
# Pattern: Web/UI
# Recommended test type: E2E

Feature: Frontend — Categories Page, Components & Navigation

  Scenario: Categories page shows loading spinner while fetching
    Given the user is authenticated and navigates to /categories
    When the category data is still loading
    Then a loading spinner is visible on the page

  Scenario: Categories render in a list with icon and name
    Given the user is authenticated as a family member
    And the family has categories: "Groceries" with icon "🛒" and "Dining" with icon "🍽️"
    When the user navigates to /categories
    Then a list of 2 categories is displayed
    And each category shows its emoji icon and name

  Scenario: Admin sees add, edit, and delete buttons
    Given the user is authenticated as a family admin
    And the family has at least one category
    When the user navigates to /categories
    Then an "Add Category" button is visible
    And each category row shows edit and delete action buttons

  Scenario: Non-admin member does not see write action buttons
    Given the user is authenticated as a non-admin family member
    And the family has at least one category
    When the user navigates to /categories
    Then no "Add Category" button is visible
    And no edit or delete buttons are visible on category rows

  Scenario: Admin creates a category via the dialog
    Given the user is authenticated as a family admin
    And the user is on the /categories page
    When the user clicks "Add Category"
    And fills in the name "Transport" and icon "🚗" in the dialog
    And clicks the submit button
    Then a success toast message appears
    And "Transport" with icon "🚗" appears in the category list

  Scenario: Empty state shows seed button for admin
    Given the user is authenticated as a family admin
    And the family has no categories
    When the user navigates to /categories
    Then a message indicating no categories exist is displayed
    And a "Seed default categories" button is visible

  Scenario: Empty state shows informational message for non-admin
    Given the user is authenticated as a non-admin family member
    And the family has no categories
    When the user navigates to /categories
    Then a message "No categories yet" is displayed
    And no "Seed default categories" button is visible

  Scenario: Categories tab in bottom navigation is enabled and navigable
    Given the user is authenticated as a family member
    When the user taps the "Categories" tab in the bottom navigation
    Then the page navigates to /categories
    And the Categories tab appears as the active tab

  Scenario: Admin edits a category via the edit dialog
    Given the user is authenticated as a family admin
    And a category named "Food" exists
    When the user clicks the edit button on the "Food" category
    And changes the name to "Groceries" in the edit dialog
    And clicks save
    Then a success toast message appears
    And the category name updates to "Groceries" in the list

  Scenario: Admin deletes a category with confirmation
    Given the user is authenticated as a family admin
    And a category named "Temporary" exists with no expenses
    When the user clicks the delete button on "Temporary"
    And confirms the deletion in the confirmation dialog
    Then a success toast message appears
    And "Temporary" is no longer visible in the category list
