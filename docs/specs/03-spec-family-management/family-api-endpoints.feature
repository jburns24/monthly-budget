# Source: docs/specs/03-spec-family-management/03-spec-family-management.md
# Pattern: API
# Recommended test type: Integration

Feature: Family API Endpoints

  Scenario: POST /api/families creates family and returns 201
    Given the API server is running
    And a registered user is authenticated with a valid JWT
    And the user is not a member of any family
    When a POST request is sent to /api/families with body {"name": "Burns Household", "timezone": "America/Chicago"}
    Then the response status is 201
    And the response body contains the family id, name, and timezone
    And the user is listed as an admin member of the new family

  Scenario: POST /api/families returns 409 when user already in a family
    Given the API server is running
    And a registered user is authenticated and already belongs to a family
    When a POST request is sent to /api/families with body {"name": "Second Family"}
    Then the response status is 409

  Scenario: GET /api/families/{family_id} returns family details for a member
    Given the API server is running
    And a family exists with two members
    And the authenticated user is a member of that family
    When a GET request is sent to /api/families/{family_id}
    Then the response status is 200
    And the response body contains the family name
    And the response body contains a member list with each member's name and role

  Scenario: GET /api/families/{family_id} returns 403 for non-member
    Given the API server is running
    And a family exists
    And the authenticated user is not a member of that family
    When a GET request is sent to /api/families/{family_id}
    Then the response status is 403

  Scenario: POST /api/families/{family_id}/invites returns generic success for any email
    Given the API server is running
    And the authenticated user is an admin of a family
    When a POST request is sent to /api/families/{family_id}/invites with body {"email": "unknown@example.com"}
    Then the response status is 200
    And the response body contains "If a user with that email exists, they will receive an invitation."

  Scenario: POST /api/families/{family_id}/invites returns same message for valid email
    Given the API server is running
    And the authenticated user is an admin of a family
    And a second registered user exists with email "valid@example.com"
    When a POST request is sent to /api/families/{family_id}/invites with body {"email": "valid@example.com"}
    Then the response status is 200
    And the response body contains "If a user with that email exists, they will receive an invitation."
    And a pending invite record exists in the database for that user

  Scenario: POST invite endpoint returns 403 for non-admin member
    Given the API server is running
    And the authenticated user is a member (not admin) of a family
    When a POST request is sent to /api/families/{family_id}/invites with body {"email": "someone@example.com"}
    Then the response status is 403

  Scenario: GET /api/invites returns pending invites for current user
    Given the API server is running
    And the authenticated user has two pending invites and one declined invite
    When a GET request is sent to /api/invites
    Then the response status is 200
    And the response body contains exactly 2 invite entries
    And each invite includes the family name and inviter info

  Scenario: POST /api/invites/{invite_id}/respond accepts invite
    Given the API server is running
    And the authenticated user has a pending invite to a family
    When a POST request is sent to /api/invites/{invite_id}/respond with body {"action": "accept"}
    Then the response status is 200
    And the user is now a member of that family with role "member"

  Scenario: POST /api/invites/{invite_id}/respond declines invite
    Given the API server is running
    And the authenticated user has a pending invite to a family
    When a POST request is sent to /api/invites/{invite_id}/respond with body {"action": "decline"}
    Then the response status is 200
    And the invite status is "declined"
    And the user is not a member of that family

  Scenario: DELETE /api/families/{family_id}/members/{user_id} removes member
    Given the API server is running
    And the authenticated user is an admin of a family with a second member
    When a DELETE request is sent to /api/families/{family_id}/members/{second_user_id}
    Then the response status is 200
    And the second user is no longer a member of the family

  Scenario: DELETE member endpoint returns 403 for non-admin
    Given the API server is running
    And the authenticated user is a member (not admin) of a family
    When a DELETE request is sent to /api/families/{family_id}/members/{another_user_id}
    Then the response status is 403

  Scenario: PATCH /api/families/{family_id}/members/{user_id} changes role
    Given the API server is running
    And the authenticated user is an admin of a family
    And a second user is a member with role "member"
    When a PATCH request is sent to /api/families/{family_id}/members/{second_user_id} with body {"role": "admin"}
    Then the response status is 200
    And the second user's role is now "admin"

  Scenario: PATCH role endpoint blocks demotion of last admin
    Given the API server is running
    And a family has exactly one admin (the owner)
    And the authenticated user is that admin
    When a PATCH request is sent to /api/families/{family_id}/members/{owner_id} with body {"role": "member"}
    Then the response status is 403

  Scenario: POST /api/families/{family_id}/leave removes current user
    Given the API server is running
    And the authenticated user is a non-owner member of a family
    When a POST request is sent to /api/families/{family_id}/leave
    Then the response status is 200
    And the user is no longer a member of the family

  Scenario: POST leave endpoint blocks owner from leaving
    Given the API server is running
    And the authenticated user is the owner of a family
    When a POST request is sent to /api/families/{family_id}/leave
    Then the response status is 403

  Scenario: GET /api/me includes family info for a family member
    Given the API server is running
    And the authenticated user belongs to a family with role "admin"
    When a GET request is sent to /api/me
    Then the response status is 200
    And the response body contains a "family" field with the family id, name, and role "admin"

  Scenario: GET /api/me returns null family for user without family
    Given the API server is running
    And the authenticated user does not belong to any family
    When a GET request is sent to /api/me
    Then the response status is 200
    And the response body contains "family": null
