# Source: docs/specs/03-spec-family-management/03-spec-family-management.md
# Pattern: State + API
# Recommended test type: Integration

Feature: Database — Families, Members & Invites

  Scenario: Alembic migration creates family tables and is reversible
    Given the database has all prior migrations applied
    When alembic upgrade head is executed
    Then the "families" table exists with columns id, name, timezone, edit_grace_days, created_by, created_at
    And the "family_members" table exists with columns id, family_id, user_id, role, joined_at
    And the "invites" table exists with columns id, family_id, invited_user_id, invited_by, status, created_at, responded_at
    When alembic downgrade -1 is executed
    Then the "families", "family_members", and "invites" tables no longer exist

  Scenario: Family model creates a valid family record
    Given a registered user exists in the database
    When a Family record is created with name "Burns Household" and created_by set to that user
    Then the family record is persisted with timezone defaulting to "America/New_York"
    And the family record has edit_grace_days defaulting to 7
    And the created_at timestamp is set automatically

  Scenario: FamilyMember unique constraint prevents duplicate membership
    Given a family exists and a user is already a member of that family
    When a second FamilyMember record is inserted for the same family_id and user_id
    Then a database integrity error is raised
    And only one membership record exists for that user in that family

  Scenario: FamilyMember role check constraint rejects invalid roles
    Given a family exists in the database
    When a FamilyMember record is inserted with role "superadmin"
    Then a database check constraint violation is raised
    And the record is not persisted

  Scenario: Invite unique constraint prevents duplicate pending invites
    Given a family exists and a pending invite already exists for a specific user
    When a second invite is inserted for the same family_id, invited_user_id, and status "pending"
    Then a database integrity error is raised
    And only one pending invite exists for that user in that family

  Scenario: Cascade delete removes members and invites when family is deleted
    Given a family exists with two members and one pending invite
    When the family record is deleted from the database
    Then no family_members records exist for that family_id
    And no invites records exist for that family_id
