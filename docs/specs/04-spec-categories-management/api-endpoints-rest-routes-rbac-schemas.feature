# Source: docs/specs/04-spec-categories-management/04-spec-categories-management.md
# Pattern: API
# Recommended test type: Integration

Feature: API Endpoints — REST Routes with RBAC & Pydantic Schemas

  Scenario: GET returns active categories for a family member
    Given a family exists with 3 active categories and 1 archived category
    And a user is authenticated as a member of that family
    When a GET request is sent to /api/families/{family_id}/categories
    Then the response status is 200
    And the response body contains 3 categories
    And no archived categories are included in the response

  Scenario: POST creates a category for an admin user
    Given a user is authenticated as an admin of a family
    When a POST request is sent to /api/families/{family_id}/categories with body {"name": "Groceries", "icon": "🛒", "sort_order": 1}
    Then the response status is 201
    And the response body contains id, family_id, name "Groceries", icon "🛒", sort_order 1, is_active true, and created_at

  Scenario: POST returns 403 for a non-admin member
    Given a user is authenticated as a non-admin member of a family
    When a POST request is sent to /api/families/{family_id}/categories with body {"name": "Test"}
    Then the response status is 403

  Scenario: PUT updates category fields for an admin user
    Given a family exists with a category named "Food"
    And a user is authenticated as an admin of that family
    When a PUT request is sent to /api/families/{family_id}/categories/{category_id} with body {"name": "Groceries"}
    Then the response status is 200
    And the response body contains name "Groceries"

  Scenario: DELETE hard-deletes a category with no expenses
    Given a family exists with a category "Temporary" that has no expense references
    And a user is authenticated as an admin of that family
    When a DELETE request is sent to /api/families/{family_id}/categories/{category_id}
    Then the response status is 200
    And the response body contains deleted true

  Scenario: DELETE archives a category that has expenses
    Given a family exists with a category "Dining" that has expense references
    And a user is authenticated as an admin of that family
    When a DELETE request is sent to /api/families/{family_id}/categories/{category_id}
    Then the response status is 200
    And the response body contains deleted false, archived true, and a non-zero expense_count

  Scenario: Seed endpoint creates default categories for admin
    Given a user is authenticated as an admin of a family with no categories
    When a POST request is sent to /api/families/{family_id}/categories/seed
    Then the response status is 200
    And the response body contains created_count 6

  Scenario: Non-member receives 404 for privacy
    Given a user is authenticated but is not a member of family X
    When a GET request is sent to /api/families/{family_x_id}/categories
    Then the response status is 404
    And the response body contains "Family not found"

  Scenario: POST validates category name constraints
    Given a user is authenticated as an admin of a family
    When a POST request is sent to /api/families/{family_id}/categories with body {"name": ""}
    Then the response status is 422
    And the response body contains a validation error for the name field
