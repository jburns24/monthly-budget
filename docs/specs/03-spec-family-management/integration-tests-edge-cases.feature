# Source: docs/specs/03-spec-family-management/03-spec-family-management.md
# Pattern: API + State
# Recommended test type: Integration

Feature: Integration Tests & Edge Cases

  Scenario: Full family lifecycle end-to-end
    Given the API server is running with a clean database
    And two registered users "Alice" and "Bob" exist
    When Alice sends a POST request to /api/families with body {"name": "Alice Family"}
    Then the response status is 201
    When Alice sends a POST request to /api/families/{family_id}/invites with body {"email": "bob@example.com"}
    Then the response status is 200
    When Bob sends a GET request to /api/invites
    Then Bob sees one pending invite for "Alice Family"
    When Bob sends a POST request to /api/invites/{invite_id}/respond with body {"action": "accept"}
    Then the response status is 200
    When Alice sends a GET request to /api/families/{family_id}
    Then the member list contains both "Alice" with role "admin" and "Bob" with role "member"
    When Alice sends a PATCH request to /api/families/{family_id}/members/{bob_id} with body {"role": "admin"}
    Then Bob's role is updated to "admin"
    When Alice sends a DELETE request to /api/families/{family_id}/members/{bob_id}
    Then Bob is removed from the family
    And the member list contains only "Alice"

  Scenario: Privacy-preserving invite returns same response for any email
    Given the API server is running
    And a family exists with an admin user "Alice"
    And no user with email "ghost@example.com" is registered
    And a user "Bob" with email "bob@example.com" is registered
    When Alice invites "ghost@example.com" to the family
    Then the response status is 200 with message "If a user with that email exists, they will receive an invitation."
    When Alice invites "bob@example.com" to the family
    Then the response status is 200 with the identical message text
    And the response shape and timing are indistinguishable between the two requests

  Scenario: One-family constraint blocks creating a second family
    Given the API server is running
    And user "Alice" is a member of family "Alpha"
    When Alice sends a POST request to /api/families with body {"name": "Beta"}
    Then the response status is 409
    And Alice remains a member of family "Alpha" only

  Scenario: One-family constraint blocks accepting invite when already in a family
    Given the API server is running
    And user "Alice" is a member of family "Alpha"
    And Alice has a pending invite to family "Beta"
    When Alice sends a POST request to /api/invites/{invite_id}/respond with body {"action": "accept"}
    Then the response status is 409
    And Alice remains a member of family "Alpha" only
    And the invite to family "Beta" remains in "pending" status

  Scenario: Owner cannot be removed from family
    Given the API server is running
    And a family exists with owner "Alice" (admin) and member "Bob" (admin)
    When Bob sends a DELETE request to /api/families/{family_id}/members/{alice_id}
    Then the response status is 403
    And Alice remains a member and admin of the family

  Scenario: Owner cannot leave family
    Given the API server is running
    And a family exists with owner "Alice"
    When Alice sends a POST request to /api/families/{family_id}/leave
    Then the response status is 403
    And Alice remains a member of the family

  Scenario: Owner cannot be demoted from admin
    Given the API server is running
    And a family exists with owner "Alice" (admin) and member "Bob" (admin)
    When Bob sends a PATCH request to /api/families/{family_id}/members/{alice_id} with body {"role": "member"}
    Then the response status is 403
    And Alice's role remains "admin"

  Scenario: Last admin cannot be demoted
    Given the API server is running
    And a family exists with exactly one admin "Alice" and one member "Bob"
    When Alice sends a PATCH request to /api/families/{family_id}/members/{alice_id} with body {"role": "member"}
    Then the response status is 403
    And Alice's role remains "admin"

  Scenario: Frontend family creation and member display with mocked API
    Given the React app is rendered with mocked API responses
    And the /api/me mock returns a user with no family
    When the user navigates to /family
    Then the "Create Family" form is displayed
    When the user fills in "Test Family" and submits the form
    And the /api/me mock is updated to return a family with members
    Then the family dashboard is displayed with the member list showing the correct names and roles
