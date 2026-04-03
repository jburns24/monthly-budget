# Source: docs/specs/03-spec-family-management/03-spec-family-management.md
# Pattern: API
# Recommended test type: Integration

Feature: Service Layer & RBAC Dependencies

  Scenario: create_family succeeds for user with no family
    Given a registered user who is not a member of any family
    When create_family is called with name "Burns Household" for that user
    Then a new family record is created with the given name
    And the user is added as a member with role "admin"
    And the family's created_by field references that user

  Scenario: create_family rejects user already in a family
    Given a registered user who is already a member of a family
    When create_family is called for that user
    Then a 409 Conflict error is returned
    And no new family record is created

  Scenario: invite_user silently succeeds for non-existent email
    Given a family exists with an admin user
    When invite_user is called with email "nobody@example.com" that does not match any registered user
    Then the method returns a generic success result
    And no invite record is created in the database

  Scenario: invite_user creates pending invite for valid eligible user
    Given a family exists with an admin user
    And a second registered user exists who is not in any family
    When invite_user is called with the second user's email
    Then a pending invite record is created linking the family to the invited user
    And the invite status is "pending"

  Scenario: invite_user silently succeeds when target user is already in a family
    Given a family "Alpha" exists with an admin
    And a second user is already a member of family "Beta"
    When invite_user is called on family "Alpha" with the second user's email
    Then the method returns a generic success result
    And no invite record is created

  Scenario: respond_to_invite accept adds user to family
    Given a user has a pending invite to a family
    When respond_to_invite is called with action "accept"
    Then the user is added as a member of the family with role "member"
    And the invite status is updated to "accepted"
    And the invite responded_at timestamp is set

  Scenario: respond_to_invite accept rejects user already in a family
    Given a user is already a member of family "Alpha"
    And the user has a pending invite to family "Beta"
    When respond_to_invite is called with action "accept" for family "Beta"
    Then a 409 Conflict error is returned
    And the user remains a member of family "Alpha" only
    And the invite status remains "pending"

  Scenario: respond_to_invite decline updates status without adding member
    Given a user has a pending invite to a family
    When respond_to_invite is called with action "decline"
    Then the invite status is updated to "declined"
    And the user is not added as a member of the family

  Scenario: remove_member is blocked for the family owner
    Given a family exists with the owner as an admin member
    When remove_member is called targeting the owner
    Then a 403 Forbidden error is returned
    And the owner remains a member of the family

  Scenario: remove_member succeeds for a non-owner member
    Given a family exists with an owner-admin and a second member
    When remove_member is called targeting the second member by an admin
    Then the second member's family_members record is deleted
    And the family has one fewer member

  Scenario: change_role prevents demoting the last admin
    Given a family exists with exactly one admin (the owner)
    When change_role is called to set the owner's role to "member"
    Then a 403 Forbidden error is returned
    And the owner's role remains "admin"

  Scenario: change_role promotes a member to admin
    Given a family exists with an owner-admin and a second member with role "member"
    When change_role is called to set the second member's role to "admin"
    Then the second member's role is updated to "admin"

  Scenario: leave_family is blocked for the owner
    Given a family exists and the current user is the owner
    When leave_family is called by the owner
    Then a 403 Forbidden error is returned
    And the owner remains a member of the family

  Scenario: leave_family succeeds for a non-owner member
    Given a family exists and the current user is a non-owner member
    When leave_family is called by that member
    Then the member's family_members record is deleted

  Scenario: require_family_member rejects non-member
    Given a family exists and a user is not a member of that family
    When a request is made to a route protected by require_family_member for that family
    Then a 403 Forbidden response is returned

  Scenario: require_family_admin rejects non-admin member
    Given a family exists and a user is a member with role "member"
    When a request is made to a route protected by require_family_admin for that family
    Then a 403 Forbidden response is returned
